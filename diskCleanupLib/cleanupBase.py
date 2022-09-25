import abc
from subprocess import Popen, PIPE, STDOUT
import traceback
import re
import os
import stat

class PurgatoryFolder:
    def __init__(self, path):
        self.path = path


class cleanupBase(metaclass=abc.ABCMeta):
    # defaults
    dryrun = 1
    verbose = 1
    startdays = 365 # the age to start cleaning purgatory from
    mindays = 30 # the youngest that can be cleaned from purgatory
    maxfull = 97 # how much % space should be used before cleaning purgatory
    purgatories = []

    def __init__(self):
        self._current_cmd = ''
        self._last_cmd_called = ''
        self._last_cmd_outs = ''
        self._last_cmd_errs = ''
        self._last_cmd_errcode = 0
        try:
            print("\nstarting cleanup " + (self.call('date', True)).strip() + ", quota: " + self.quota_string())
            self.init()
            self.run_cleanup()
            self.cleanup_purgatories()
            print("finished cleanup " + (self.call('date', True)).strip() + ", quota: " + self.quota_string() + "\n")
        except Exception as e:
            print(self.__dict__)
            raise

    def init(self):
        pass

    @abc.abstractmethod
    def run_cleanup(self):
        pass

    def _cleanup_purgatories(self, days):
        mtime = int(days - 1)
        if self.verbose:
            print("deleting "+str(days)+" days old files from", len(self.purgatories), "purgatory folders")
        num_results = 0
        for p in self.purgatories:
            res = self.find_delete(p.path, '-mindepth 1 -type f -mtime +'+str(mtime))
            num_results += len(res)
        return num_results

    def cleanup_purgatories(self):
        print('==== cleanup', len(self.purgatories), 'purgatory folders')
        if len(self.purgatories) == 0:
            return
        
        purgatory_cleaned_up = 0
        days = self.startdays
        while self.needs_cleanup(days):
            purgatory_cleaned_up += self._cleanup_purgatories(days)
            #days -= int(max(1, days*0.1 ))
            days -= 1
            if self.dryrun and purgatory_cleaned_up>50:
                break

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
            raise RuntimeError(cmd+' return code: '+str(ret))
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
        space = values[2]
        quota = values[3]
        return int(space), int(quota)


    def calc_quota(self):
        try:
            output = self.call('quota', True)
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
        print('move('+base+', '+from_path+', '+to_path+', '+str(touch)+')')
        dirname = self._call('dirname '+to_path+'"'+from_path+'"')
        dirname = dirname.strip()
        self.call('mkdir -p "'+dirname+'"')
        self.call('mv '+base+'"'+from_path+'" '+to_path+'"'+from_path+'"')


    def move_old(self, from_path, to_path, age):
        if not os.path.isdir(from_path):
            print('move_old', from_path, 'does not exist')
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
        if not os.path.isdir(path):
            print('delete_empty', path, 'does not exist')
            return None
        return self.call('find '+path+' -mindepth '+str(mindepth)+' -maxdepth '+str(maxdepth)+' -type d -empty -delete')


    def delete_old_dupes(self, path, age):
        print('delete_old_dupes('+path+', '+str(age)+')')
        self.find_delete(path, '-links +1 -type f -mtime +'+str(age-1))
        self.delete_empty(path, 1)


    def find_delete(self, path, arguments):
        if not os.path.isdir(path):
            print('find_delete', path, 'does not exist')
            return None
        cmd = 'find '+path+' '+arguments+' -exec echo "deleting {}" \\; -exec rm -rf "{}" \\;'
        out = self.call(cmd)
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
