import time
from apscheduler.schedulers.blocking import BlockingScheduler
import backend
import os
import sys
import atexit

# --- Lock File Mechanism to prevent duplicate schedulers ---
LOCK_FILE = "scheduler.lock"

def create_lock_file():
    if os.path.exists(LOCK_FILE):
        print("Scheduler is already running. Exiting.")
        sys.exit()
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def remove_lock_file():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        print("Scheduler lock file removed.")

# Register the cleanup function to be called on exit
atexit.register(remove_lock_file)
# --- End of Lock File Mechanism ---


def run_polling():
    """Wrapper function for the polling cycle job."""
    print("Scheduler: Running polling cycle...")
    backend.run_polling_cycle()

def schedule_jobs(scheduler):
    """Loads config and sets up all scheduled jobs."""
    print("Loading configuration and setting up jobs...")
    config = backend.load_config()

    # Clear existing jobs to handle config changes
    for job in scheduler.get_jobs():
        job.remove()

    # 1. Schedule the main data polling cycle
    polling_interval = config.get('globalPollingIntervalMinutes', 15)
    scheduler.add_job(run_polling, 'interval', minutes=polling_interval, id='polling_cycle')
    print(f"Scheduled data polling to run every {polling_interval} minutes.")

    # 2. Schedule each individual export destination
    for destination in config.get('exportDestinations', []):
        dest_name = destination.get('name', '').strip()
        if not dest_name:
            print("Skipping export with no name.")
            continue
            
        freq = destination.get('runFrequency', 1)
        unit = destination.get('runFrequencyUnit', 'hours') # e.g., 'minutes', 'hours', 'days'
        
        job_id = f"export_{dest_name.replace(' ', '_')}"

        # Use a lambda to pass the specific destination config to the job function
        job_function = lambda d=destination: backend.run_single_export(d, is_manual_run=False)

        scheduler.add_job(job_function, 'interval', **{unit: freq}, id=job_id)
        print(f"Scheduled export '{dest_name}' to run every {freq} {unit}.")

if __name__ == '__main__':
    # Create the lock file to ensure single instance
    create_lock_file()

    # Initialize scheduler
    scheduler = BlockingScheduler()
    
    # Perform an initial run of polling to get data immediately
    run_polling()
    
    # Initial setup of jobs
    schedule_jobs(scheduler)
    
    print("Scheduler started. Press Ctrl+C to exit.")
    
    try:
        # Start the scheduler's main loop
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler shutting down.")

