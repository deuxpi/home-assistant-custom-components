from setuptools import setup, find_packages

setup(
    name='homeassistant-custom-components',
    description='Home Assistant custom components',
    version='0.1',
    url='https://github.com/deuxpi/home-assistant-custom-components',
    author='Philippe Gauthier',
    author_email='philippe.gauthier@deuxpi.ca',
    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'homeassistant==0.88.2'
    ],
    test_suite='tests'
)
