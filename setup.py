#!/usr/bin/env python

from setuptools import setup, find_packages
import os
import sys

here = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(here, 'README.rst')) as f:
        README = f.read()
except:
    README = ''


requires = []
# add argparse to be installed for earlier versions of python
if sys.version_info[:2] <= (2, 6):
    requires.append('argparse')

setup(name='ppagent',
      version='0.2.4',
      description='A statistics collection agent for powerpool mining server',
      author='Isaac Cook',
      long_description=README,
      author_email='isaac@simpload.com',
      url='http://www.python.org/sigs/distutils-sig/',
      packages=find_packages(),
      install_requires=requires,
      package_data={'ppagent': ['install/*']},
      entry_points={
          'console_scripts': [
              'ppagent = ppagent.main:entry'
          ]
      }
      )
