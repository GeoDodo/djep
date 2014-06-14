# -*- coding: utf-8 -*-
import functools
from os.path import join, splitext

from fabric.api import *
from fabric.contrib import files, project

if not env.get('branch'):
    abort("Please select a config file (staging.ini | production.ini)")
env.hosts = ['root@134.119.9.21', ]
env.srv_user = 'fossgis'
env.proj_name = 'pyconde'
env.www_root = join(env.root, 'htdocs')
env.proj_root = join(env.root, 'djep')
env.manage_py = join(env.proj_root, 'manage.py')


def srv_run(cmd):
    return sudo("{envdirbin} {envdir} {cmd}".format(
        envdirbin=join(env.root, 'bin', 'envdir'),
        envdir=join(env.root, 'env'),
        cmd=cmd
        ), user=env.srv_user)

def srv_open_shellfa(cmd):
    return open_shell('sudo -u %s -s -- %s' % (env.srv_user, cmd))


def ve_python(cmd):
    return srv_run('%s %s' % (join(env.root, 'bin', 'python'), cmd))


def manage_py(cmd):
    return ve_python('%s %s' % (join(env.proj_root, 'manage.py'), cmd))


def supervisorctl(cmd):
    return srv_run('%s %s' % (join(env.root, 'bin', 'supervisorctl'), cmd))

@task
def compilemessages():
    """Compile the i18n messages."""
    with cd(join(env.proj_root, env.proj_name)):
        manage_py('compilemessages')
    # We have to compile the JavaScript messages within their respective app.
    with cd(join(env.proj_root, env.proj_name, 'core')):
        manage_py('compilemessages')


@task
def upgrade():
    """
    Upgrades the server to the latest codebase.
    """
    update_proj()
    update_requirements()
    syncdb()
    migrate()
    build_static_files()
    compilemessages()
    restart_celery()
    restart_worker()
    # build_docs()


@task
def syncdb():
    """
    Executes python manage.py syncdb on the server.
    """
    manage_py('syncdb -v 0 --noinput')


@task
def migrate():
    """
    Executes python manage.py migrate on the server.
    """
    manage_py('migrate -v 0 --noinput')


@task
def update_requirements():
    """
    Updates the project's requirements based on the requirements.txt file.
    """
    pip = join(env.root, 'bin', 'pip')
    requirements = join(env.proj_root, 'requirements', '{0}.txt'.format(
        env.environment))
    srv_run('%s install -q --use-mirrors -r %s' % (pip, requirements))


@task
def update_proj():
    """
    Fetches changes from the repository.
    """
    with cd(env.proj_root):
        srv_run('git pull')
        srv_run('git checkout -f %s' % env.branch)


@task
def build_static_files():
    """
    Compiles less files into css, runs collectstatic and compress.
    """
    with cd(env.proj_root):
        srv_run('npm install')
        with cd(env.proj_root + '/pyconde/skins/fg15/static/assets'):
            srv_run('../../../../../node_modules/bower/bin/bower install')
        with path('/srv/pyep/.gem/ruby/1.8/bin/', behavior='prepend'):
            srv_run('./node_modules/grunt-cli/bin/grunt compass:dist')
    manage_py('compilejsi18n')
    manage_py('collectstatic --noinput -v1')
    manage_py('compress --force')


@task
def restart_worker():
    """
    Restarts the gunicorn workers managed by supervisord.
    """
    return supervisorctl('restart site')


@task
def restart_celery():
    """
    Restarts the gunicorn workers managed by supervisord.
    """
    return supervisorctl('restart celery')


@task
def djshell():
    """
    Starts a Django shell on the server.
    """
    return srv_open_shell('%s %s shell' % (
        join(env.root, 'bin', 'python'),
        join(env.proj_root, 'manage.py')))


@task
def loaddata(fixture):
    """
    Loads a given fixture name.
    """
    manage_py('loaddata {0}'.format(fixture))


@task
def build_docs():
    """
    Rebuilds the sphinx documentation on the server.
    """
    with cd(join(env.proj_root, 'docs')):
        srv_run("source ../../bin/activate && make html")


@task
def make_dirs():
    sudo('mkdir -p /opt')
    sudo('mkdir -p /opt/konferenz')


# todo check missing packages and update fab commands
@task
def install_deps():
    with shell_env(DEBIAN_FRONTEND='readline'):
        sudo('aptitude install -y -q'
            ' python-dev tmux python-setuptools libpq-dev git gettext'
            ' redis-server nodejs python-virtualenv python-lxml'
            ' libxslt1-dev libxslt1.1 libxml2-dev libxml2 libssl-dev'
            ' postgresql-9.3-postgis-2.1 postgresql-client-9.3'
        )

@task
def install_venv(upgrade=False, upgrade_venv=False):
    venv = '/opt/konferenz'
    if not files.exists(venv + '/bin/pip') or upgrade_venv:
        run('virtualenv ' + venv)

    put('requirements/base.txt', venv)
    put('requirements/production.txt', venv)

    upgrade = '--upgrade' if upgrade else ''

    with cd(venv):
        run('bin/pip install -r production.txt')