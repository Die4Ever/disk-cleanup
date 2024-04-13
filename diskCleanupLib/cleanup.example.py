import os
from diskCleanupLib.cleanupBase import cleanupBase, PurgatoryFolder

class Cleanup(cleanupBase):
    verbose = 1
    startdays = 365 # the age to start cleaning purgatory from
    mindays = 30 # the youngest that can be cleaned from purgatory
    maxfull = 97 # how much % space should be used before cleaning purgatory
    purgatory_age = 10 # when to move files to purgatory
    purgatories = [PurgatoryFolder('~/purgatory')]

    def run_cleanup(self):
        self.delete_empty('~/downloads/', mindepth=1, maxdepth=1)

        self.delete_old_files('~/7days/', 7)

        if self.verbose:
            print('==== move to purgatory')

        self.move_old('~/downloads/', '~/purgatory/', self.purgatory_age)
