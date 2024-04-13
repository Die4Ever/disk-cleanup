import abc
from subprocess import Popen, PIPE, STDOUT
import traceback
import re
import os
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description='Disk Cleanup Utility by Die4Ever')
parser.add_argument('--wetrun', action="store_true", help='The opposite of dryrun, we default to dryrun for safety.')
parser.add_argument('--max-purgatory-days', help='Delete anything in purgatory folders older than this number of days.')
args = parser.parse_args()

class PurgatoryFolder:
    def __init__(self, path):
        self.path = path


class CmdException(RuntimeError):
    pass


class cleanupBase(metaclass=abc.ABCMeta):
    # defaults
    dryrun = 1
    verbose = 1
    startdays = 365 # the age to start cleaning purgatory from
    mindays = 30 # the youngest that can be cleaned from purgatory
    maxfull = 97 # how much % space should be used before cleaning purgatory
    purgatories = []

    def __init__(self):
        global args
        self._current_cmd = ''
        self._last_cmd_called = ''
        self._last_cmd_outs = ''
        self._last_cmd_errs = ''
        self._last_cmd_errcode = 0
        try:
            if args.wetrun:
                self.dryrun = 0
            print("\nstarting", ('dryrun' if self.dryrun else 'wetrun') , "cleanup", (self.call('date', True)).strip(), ", quota:", self.quota_string())
            self.init()
            self.run_cleanup()
        except Exception as e:
            print(self.__dict__)
            raise
        finally:
            self.cleanup_purgatories()
            print("finished", ('dryrun' if self.dryrun else 'wetrun') , "cleanup", (self.call('date', True)).strip(), ", quota:", self.quota_string(), "\n")

    def init(self):
        pass

    @abc.abstractmethod
    def run_cleanup(self):
        pass

    def _cleanup_purgatories(self, days):
        mtime = int(days - 1)
        if self.verbose:
            print('deleting', days, 'days old files from', len(self.purgatories), 'purgatory folders')
        num_results = 0
        for p in self.purgatories:
            res = self.find_delete(p.path, '-mindepth 1 -type f -mtime +'+str(mtime))
            num_results += len(res.splitlines())
        return num_results

    def cleanup_purgatories(self):
        global args
        print('==== cleanup', len(self.purgatories), 'purgatory folders')
        if len(self.purgatories) == 0:
            return
        
        purgatory_cleaned_up = 0
        days = self.startdays
        if args.max_purgatory_days is not None:
            days = int(args.max_purgatory_days)
            purgatory_cleaned_up += self._cleanup_purgatories(days)
            days -= 1
        
        while self.needs_cleanup(days):
            purgatory_cleaned_up += self._cleanup_purgatories(days)
            #days -= int(max(1, days*0.1 ))
            days -= 1
            if self.dryrun and purgatory_cleaned_up>50:
                break
        
        if purgatory_cleaned_up:
            days += 1
            print('cleaned up', purgatory_cleaned_up, 'files that were', days, 'days old')

        for p in self.purgatories:
            self.delete_empty(p.path, 1)

    def _call(self, cmd, safe=False):
        self._current_cmd = cmd
        if self.verbose:
            print(cmd)

        if self.dryrun and not safe:
            if ' rm -rf ' in cmd:
                cmd = cmd.replace(' rm -rf ', ' echo ')
            elif ' -delete' in cmd:
                cmd = cmd.replace(' -delete', ' -exec echo "{}" \\;')
            elif ' -exec mv "{}"' in cmd:
                cmd = cmd.replace(' -exec mv "{}"', ' -exec echo "{}"')
            else:
                print("not running command due to dryrun: "+cmd)
                return ''

        self._current_cmd = cmd
        #p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True, text=True)
        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True, universal_newlines=True)
        outs=''
        errs=''

        try:
            outs, errs = p.communicate(timeout=300)
        except Exception as e:
            p.kill()
            print(traceback.format_exc())
            raise

        if self.verbose:
            print(outs)

        if len(errs) > 0:
            print('got errs')
            print(errs)
        ret = p.returncode
        self._last_cmd_called = cmd
        self._last_cmd_outs = outs
        self._last_cmd_errs = errs
        self._last_cmd_errcode = ret
        if ret != 0:
            raise CmdException(cmd+' return code: '+str(ret), cmd, ret, outs, errs)
        self._current_cmd = ''
        return outs


    def call(self, cmd, safe=False):
        try:
            return self._call(cmd, safe)
        except Exception as e:
            print(e)


    def get_space(self, output):
        lines = output.splitlines()
        values = re.split(r'\s+', lines[2])
        space = values[2].replace('*','')
        quota = values[3].replace('*','')
        return int(space), int(quota)


    def calc_quota(self):
        try:
            output = self.call('quota || true', True)
            space, quota = self.get_space(output)
            percent = space / quota * 100
            if self.verbose:
                print( str(space) +" / "+ str(quota) +" == "+ str(percent) +"%")
            return percent
        except Exception as e:
            print(traceback.format_exc())
            return 0


    def quota_string(self):
        return "{:0.2f}%".format(self.calc_quota())
        #return str(round(calc_quota(), 2)) + "%"


    def move(self, base, from_path, to_path, touch=False):
        # retain folder structure
        f = Path(base, from_path).expanduser()
        t = Path(to_path, from_path).expanduser()
        print('move: ', f, ' -> ', t)
        t.parent.mkdir(parents=True, exist_ok=True)

        if f.exists() and t.exists():
            if f.samefile(t):
                print('source and destination are the same inode!', f, t)
                print('deleting source!')
                if not self.dryrun:
                    f.unlink()
                return
            print('destination exists, overwriting...')
        if not self.dryrun:
            f.replace(t)


    def move_old(self, from_path, to_path, age):
        if not self.isdir(from_path, 'move_old'):
            return
        count = 0
        files = self.call('cd '+from_path+' ; find . -type f -mindepth 1 -mtime +'+str(age-1), True)
        for file in files.split('\n')[::-1]:
            file = file.strip()
            if file == '':
                continue

            if count == 0:
                print('')
                print('move_old('+from_path+', '+to_path+', '+str(age)+')')

            count += 1
            file = re.sub(r'^\./', '', file)
            self.move(from_path, file, to_path)
        self.delete_empty(from_path, 1)
        if count > 0:
            print('')


    def delete_empty(self, path, mindepth, maxdepth=100):
        if not self.isdir(path, 'delete_empty'):
            return None
        return self.call('find '+path+' -mindepth '+str(mindepth)+' -maxdepth '+str(maxdepth)+' -type d -empty -delete')


    def delete_old_dupes(self, path, age):
        print('delete_old_dupes('+path+', '+str(age)+')')
        self.find_delete(path, '-links +1 -type f -mtime +'+str(age-1))
        self.delete_empty(path, 1)


    def find_delete(self, path, arguments):
        if not self.isdir(path, 'find_delete'):
            return None
        # our call function would replace the rm -rf if dryrun, but then we get double output which is annoying for the caller
        if self.dryrun:
            cmd = 'find '+path+' '+arguments+' -exec echo "dryrun delete {}" \\;'
        else:
            cmd = 'find '+path+' '+arguments+' -exec echo "deleting {}" \\; -exec rm -rf "{}" \\;'
        out = self.call(cmd, safe=True)
        if (out and len(out)) or self.verbose:
            print(cmd)
            print(out)
        return out


    def delete_old_files(self, path, age_days:int, min_depth:int=1):
        res = self.find_delete(path, '-mindepth '+str(min_depth)+' -mtime +' + str(age_days-1))
        self.delete_empty(path, 1)
        return res

    def needs_cleanup(self, days):
        used = self.calc_quota()
        if days < 0:
            return False
        if used > 99:
            return True
        if days >= self.mindays and used > self.maxfull:
            return True
        return False

    def isdir(self, path, func=''):
        path = Path(path)
        path = path.expanduser()
        if not path.is_dir():
            print(func, path, 'does not exist')
            return False
        return True
