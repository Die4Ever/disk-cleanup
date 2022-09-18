# disk-cleanup

example crontab

```
0 0 1 * * mv -f ~/purgatory/cleanup.log.txt ~/purgatory/old.cleanup.log.txt
0 * * * * ~/disk-cleanup/cleanup.py >> ~/purgatory/cleanup.log.txt
```
