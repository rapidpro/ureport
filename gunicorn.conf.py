import multiprocessing

workers = multiprocessing.cpu_count() * 2 + 1
proc_name = 'ureport'
default_proc_name = proc_name
accesslog = 'gunicorn.access'
timeout = 120
