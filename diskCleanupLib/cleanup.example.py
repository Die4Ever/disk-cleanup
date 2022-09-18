import os
import diskCleanupLib.cleanupBase

class Cleanup(diskCleanupLib.cleanupBase.cleanupBase):
    dryrun = 1
    verbose = 1
    startdays = 365
    mindays = 30
    maxfull = 97
    purgatory_age = 10

    def cleanup_purgatory(self, days):
        mtime = int(days - 1)
        if self.verbose:
            print("deleting "+str(days)+" days old files from purgatory")
        res = self.find_delete('~/purgatory/', '-mindepth 1 -type f -mtime +'+str(mtime))
        return len(res)

    def run_cleanup(self):
        self.delete_empty('~/downloads/', 1, 1)

        if self.verbose:
            print('==== cleanup purgatory')

        purgatory_cleaned_up = 0
        days = self.startdays
        while self.needs_cleanup(days):
            purgatory_cleaned_up += self.cleanup_purgatory(days)
            #days -= int(max(1, days*0.1 ))
            days -= 1
            if self.dryrun and purgatory_cleaned_up>100:
                break

        self.delete_empty('~/purgatory', 1)

        if self.verbose:
            print('==== move to purgatory')

        self.move_old('~/downloads/', '~/purgatory/', self.purgatory_age)
