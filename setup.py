#!/usr/bin/env python

from setuptools import setup, find_packages
import os

here = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(here, 'README.rst')) as f:
        README = f.read()
except:
    README = ''


setup(name='ppagent',
      version='0.2.1',
      description='A statistics collection agent for powerpool mining server',
      author='Isaac Cook',
      long_description=README,
      author_email='isaac@simpload.com',
      url='http://www.python.org/sigs/distutils-sig/',
      packages=find_packages(),
      install_requires=['argparse'],
      package_data={'ppagent': ['install/*']},
      entry_points={
          'console_scripts': [
              'ppagent = ppagent.main:entry'
          ]
      }
      )
