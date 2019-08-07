config = dict(
    port="8025",
    app_dir="ureport",
    friendly_name="UReport",
    repository="ssh://git@github.com/rapidpro/ureport.git",
    domain="ureport.in",
    name="ureport",
    repo="ureport",
    user="ureport",
    env="env",
    settings="settings.py.dev",
    dbms="psql",
    db="ureport",
    custom_domains="*.ureport.in ureport.in *.ureport.staging.nyaruka.com",
    prod_host="report1",
    sqldump=False,
    celery=True,
    processes=("celery", "sync"),
    celery_beat_process=True,
    python_cmd="python3.6",
    error_file="config/error.html",
    error_logo="config/logo.png",
    compress=True,
    region="eu-west-1",
    hosts=[
        dict(name="report1", host="report1.ureport.in", ec2_id="i-097e4a4877e9e4bd3", beat=True),
        dict(name="report2", host="report2.ureport.in", ec2_id="i-03ad184efe5ede6f2"),
    ],
    elb=[
        dict(
            name="UReport",
            arn="arn:aws:elasticloadbalancing:eu-west-1:363799401673:targetgroup/UReport/975d358d8c5a205a",
        ),
        dict(
            name="UReport SSL",
            arn="arn:aws:elasticloadbalancing:eu-west-1:363799401673:targetgroup/UReportSSL/bf470ad406b9700a",
        ),
    ],
)

excludes = (
    # these tables we just truncate completely
    {"table": "contacts_contact", "truncate": True},
    {"table": "polls_pollresult", "truncate": True},
)
