# GTFS Monthly Update Setup

This directory contains scripts for automating GTFS data updates.

## Setup Instructions

### 1. Make the update script executable
```bash
chmod +x scripts/update-gtfs-monthly.sh
```

### 2. Set up a cron job on your Raspberry Pi

SSH into your Pi and edit the crontab:
```bash
crontab -e
```

Add this line to run updates on the 1st of each month at 3 AM:
```bash
0 3 1 * * /home/aboland/gtfs-dublin/scripts/update-gtfs-monthly.sh
```

**Cron format explanation:**
```
0 3 1 * *
│ │ │ │ └─ Day of week (0-6, Sunday=0) — * means any day
│ │ │ └─── Month (1-12) — * means any month
│ │ └───── Day of month (1-31) — 1 means 1st of month
│ └─────── Hour (0-23) — 3 means 3 AM
└───────── Minute (0-59) — 0 means top of hour
```

### 3. Verify the cron job
```bash
crontab -l
```

You should see your new line listed.

### 4. Monitor updates

Check the log file to see update history:
```bash
tail -f ~/gtfs-dublin/gtfs-update.log
```

## Alternative Schedules

**Every Sunday at 2 AM:**
```bash
0 2 * * 0 /home/aboland/gtfs-dublin/scripts/update-gtfs-monthly.sh
```

**Every week on Monday at 3 AM:**
```bash
0 3 * * 1 /home/aboland/gtfs-dublin/scripts/update-gtfs-monthly.sh
```

**1st and 15th of each month at 3 AM:**
```bash
0 3 1,15 * * /home/aboland/gtfs-dublin/scripts/update-gtfs-monthly.sh
```

## Troubleshooting

If the script doesn't run:
1. Check cron is enabled: `sudo service cron status`
2. Verify the script path is absolute (use full paths, not ~)
3. Check logs: `grep CRON /var/log/syslog`
4. Test manually: `bash scripts/update-gtfs-monthly.sh`

## What the script does

1. Downloads latest GTFS data from Transport Ireland
2. Saves to `GTFS_Realtime/` directory
3. Restarts the transport-api container to load new data
4. Logs all activity to `gtfs-update.log`
