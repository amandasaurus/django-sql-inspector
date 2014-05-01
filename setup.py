#! /usr/bin/env python

from setuptools import setup, find_packages


setup(name="django-sql-inspector",
      version="1.0.0",
      author="Rory McCann",
      author_email="rory@technomancy.org",
      packages=['sql_inspector'],
      license = 'GPLv3',
      description = 'Analyze and measure the SQL calls, used by your Django application',
      install_requires=[ 'django>=1.4' ],
)
