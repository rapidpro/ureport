config = dict(    
    port='8025',
    app_dir='ureport',
    friendly_name='UReport',
    domain='ureport.in',
    name='ureport',
    repo='ureport',
    user='ureport',
    env='env',
    settings='settings.py.dev',
    dbms='psql',
    db='ureport',
    custom_domains='*.ureport.in ureport.in',
    prod_host='report1',
    sqldump=False,

    celery=(),

    compress=True,
    elb = dict(name='UReport',
               region='eu-west-1',
               primary='report1',
               instances=[dict(name='report1', host='report1.ureport.in', id='i-5c86951c'),
                          dict(name='report2', host='report2.ureport.in', id='i-86ab5cc4')])
)
