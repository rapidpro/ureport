config = dict(    
    port='8025',
    app_dir='ureport',
    friendly_name='UReport',
    repository='ssh://git@github.com/rapidpro/ureport.git',
    domain='ureport.in',
    name='ureport',
    repo='ureport',
    user='ureport',
    env='env',
    settings='settings.py.dev',
    dbms='psql',
    db='ureport',
    custom_domains='*.ureport.in ureport.in *.ureport.staging.nyaruka.com',
    prod_host='report1',
    sqldump=False,
    celery=True,
    processes=('celery', 'sync'),

    compress=True,
    region='eu-west-1',
    hosts=[
        dict(name='report1', host='report1.ureport.in', ec2_id='i-05375dd10219ae352'),
        dict(name='report2', host='report2.ureport.in', ec2_id='i-00a6e306e2139c753'),
    ],
    elb=[
        dict(name='UReport', arn='arn:aws:elasticloadbalancing:eu-west-1:363799401673:targetgroup/UReport/975d358d8c5a205a'),
        dict(name='UReport SSL', arn='arn:aws:elasticloadbalancing:eu-west-1:363799401673:targetgroup/UReportSSL/bf470ad406b9700a'),
    ],
)

excludes = (
    # these tables we just truncate completely
    {"table": "contacts_contact", "truncate": True},
    {"table": "polls_pollresult", "truncate": True},
)