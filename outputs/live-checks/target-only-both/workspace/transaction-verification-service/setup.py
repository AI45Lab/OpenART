#!/usr/bin/env python
from setuptools import setup, find_packages
import os

# Read version from transaction_service package
with open(os.path.join('transaction_service', '__init__.py'), 'r') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.split('=')[1].strip().strip("'").strip('"')
            break
    else:
        version = '0.0.1'

# Read long description from README
with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='transaction-verification-service',
    version=version,
    description='Service to validate payment transactions',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Payments Infrastructure Team',
    author_email='payments-infra@example.com',
    url='https://github.com/example/transaction-verification-service',
    packages=find_packages(exclude=['tests']),
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    test_suite='tests',
)