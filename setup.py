from distutils.core import setup

setup(
    name='btc_embedded',
    version='24.2.11',
    packages=['btc_embedded'],
    include_package_data=True,
    license='MIT',
    description='API wrapper for BTC EmbeddedPlatform REST API',
    long_description='API wrapper for BTC EmbeddedPlatform REST API',
    author='Thabo Krick',
    author_email='thabo.krick@btc-embedded.com',
    url='https://github.com/btc-embedded/btc_embedded',
    install_requires=[ 'requests', 'pyyaml' ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Testing',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)
