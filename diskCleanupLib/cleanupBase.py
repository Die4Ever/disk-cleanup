import abc
from subprocess import Popen, PIPE, STDOUT
import traceback
import re
import os
import stat

class cleanupBase(metaclass=abc.ABCMeta):
    # defaults
    dryrun = 1
    verbose = 1
    mindays = 30
    maxfull = 97

    def __init__(self):
        print("\nstarting cleanup " + (self.call('date', True)).strip() + ", quota: " + self.quota_string())
        self.run_cleanup()
        print("finished cleanup " + (self.call('date', True)).strip() + ", quota: " + self.quota_string() + "\n")

    @abc.abstractmethod
    def run_cleanup(self):
        return

    def _call(self, cmd, safe=False):
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
        if ret != 0:
            raise RuntimeError(cmd+' return code: '+str(ret))
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
        return self.call('find '+path+' -mindepth '+str(mindepth)+' -maxdepth '+str(maxdepth)+' -type d -empty -delete')


    def delete_old_dupes(self, path, age):
        print('delete_old_dupes('+path+', '+str(age)+')')
        self.find_delete(path, '-links +1 -type f -mtime +'+str(age-1))
        self.delete_empty(path, 1)


    def find_delete(self, path, arguments):
        cmd = 'find '+path+' '+arguments+' -exec echo "deleting {}" \\; -exec rm -rf "{}" \\;'
        out = self.call(cmd)
        if (out and len(out)) or self.verbose:
            print(cmd)
            print(out)
        return out


    def needs_cleanup(self, days):
        used = self.calc_quota()
        if days < 0:
            return False
        if used > 99:
            return True
        if days >= self.mindays and used > self.maxfull:
            return True
        return False