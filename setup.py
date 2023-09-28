from setuptools import setup

setup(
    name='btc_embedded',
    version='23.2.0',
    packages=['btc_embedded'],
    license='MIT',
    description='API wrapper for BTC EmbeddedPlatform 23.2p0 REST API',
    author='Thabo Krick',
    author_email='thabo.krick@btc-embedded.com',
    url='https://github.com/btc-embedded/btc-ci-workflow/examples/api',
    install_requires=[ 'requests', 'pyyaml' ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Testing :: Embedded Software :: Model-based :: ISO26262'
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
