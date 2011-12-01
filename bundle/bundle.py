from __future__ import absolute_import
from __future__ import with_statement

import os
import string
import sys

from contextlib import contextmanager
from shutil import rmtree
from string import Template
from subprocess import Popen, PIPE
from tempfile import mkdtemp, NamedTemporaryFile
from textwrap import TextWrapper

from . import __version__
from . import files


def indent(s, n=4):
    return "\n".join(' ' * n + line for line in s.split('\n'))


def codewrap(s, w=50, i=4):
    wrapper = TextWrapper(width=50, break_on_hyphens=False)
    lines = wrapper.wrap(s)
    return "\n".join([lines[0]] + [indent(l, i)
                                    for l in lines[1:]])


@contextmanager
def changedir(new):
    prev = os.getcwd()
    os.chdir(new)
    yield new
    os.chdir(prev)


def say(m):
    sys.stderr.write("%s\n" % (m, ))


class Version(list):
    develindex = None

    def __init__(self, value):
        value, _, self.devel = value.partition('-')
        list.__init__(self, map(int, value.split(".")))

    def __str__(self):
        return ".".join(map(str, self)) + self._develpart

    def __repr__(self):
        return str(self)

    def bump(self):
        if self.is_devel:
            raise ValueError("Can't bump development versions")
        if len(self) < 3:
            self.append(0)
        self[-1] += 1
        return self

    @property
    def is_devel(self):
        return bool(self.devel)

    @property
    def _develpart(self):
        if self.devel:
            return '-' + self.devel
        return ''


class Bundle(object):

    def __init__(self, name, description=None, requires=None, version=None,
            author=None, author_email=None, url=None, platforms=None,
            license=None, setup_template=None, readme_template=None):
        self.name = name
        self.description = description or "autogenerated bundle"
        self.requires = requires or []
        self.version = version or "1.0"
        self.author = author or ""
        self.author_email = author_email or ""
        self.url = url or ""
        self.platforms = platforms or ["all"]
        self.license = license or "BSD"
        self._setup_template = setup_template
        self._readme_template = readme_template
        self._pypi = None

    def register(self):
        self.sync_version_from_pypi()
        self.run_setup_command("register")

    def upload(self):
        self.run_setup_command("register", "sdist", "upload")

    def upload_fix(self):
        self.bump_if_already_on_pypi()
        self.upload()

    def sync_version_from_pypi(self):
        version = Version(self.version)
        prev = str(version)
        while 1:
            if not self._version_exists(version):
                self.version = prev
                return prev
            prev = str(version)
            version.bump()

    def bump_if_already_on_pypi(self):
        version = Version(self.version)
        while 1:
            if not self._version_exists(version):
                break
            version.bump()
            print("Version taken: trying next version %r" % (version, ))
        self.version = str(version)
        return self.version

    def version_exists(self):
        return self._version_exists(self.version)

    def _version_exists(self, version):
        return bool(self.pypi.release_urls(self.name, str(version)))

    def render_setup(self):
        return Template(self.setup_template).substitute(**self.stash)

    def render_readme(self):
        return Template(self.readme_template).substitute(**self.stash)

    @contextmanager
    def temporary_dir(self):
        dirname = mkdtemp()
        yield dirname
        rmtree(dirname)

    @contextmanager
    def render_to_temp(self):
        with self.temporary_dir() as dir:
            with NamedTemporaryFile(dir=dir, suffix=".py") as setup:
                with changedir(dir):
                    setup.write(self.render_setup())
                    setup.flush()
                    with open("README", "w") as readme:
                        readme.write(self.render_readme())
                    yield setup.name

    def run_setup_command(self, *argv):
        with self.render_to_temp() as setup_name:
            say(Popen([sys.executable, setup_name] + list(argv),
                       stdout=PIPE).communicate()[0])

    def upload_if_missing(self):
        if not self.version_exists():
            self.upload()

    def __repr__(self):
        return "<Bundle: %s v%s" % (self.name, self.version)

    @property
    def upload_args(self):
        return ["register", "sdist", "upload"]

    @property
    def stash(self):
        title = " - ".join([self.name, self.description])
        return dict(self.__dict__,
                    title=title,
                    title_h1='=' * len(title),
                    bundle_version=__version__,
                    requires_i2=codewrap(repr(self.requires), i=4),
                    requires_i24=codewrap(repr(self.requires), i=24))
    @property
    def setup_template(self):
        if self._setup_template is None:
            self._setup_template = files.slurp("setup.py.t")
        return self._setup_template

    @property
    def readme_template(self):
        if self._readme_template is None:
            self._readme_template = files.slurp("README.t")
        return self._readme_template

    @property
    def pypi(self):
        if self._pypi is None:
            from yolk.pypi import CheeseShop
            self._pypi = CheeseShop()
        return self._pypi

