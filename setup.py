#!/usr/bin/env python

from setuptools import setup, find_packages


setup(name='ppagent',
      version='0.1',
      description='A statistics collection agent for powerpool mining server',
      author='Isaac Cook',
      author_email='isaac@simpload.com',
      url='http://www.python.org/sigs/distutils-sig/',
      packages=find_packages(),
      entry_points={
          'console_scripts': [
              'ppagent = ppagent.main:entry'
          ]
      }
      )
