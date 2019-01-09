#!/usr/bin/env python

from __future__ import print_function

import fcntl
import json
import os
import sys

from argparse import ArgumentParser
from contextlib import contextmanager
from os import path

LOCK_FILE = '/var/lib/securedrop/securedrop-config-migrate.lock'
CONFIG_DIR = '/etc/securedrop'


@contextmanager
def acquire_lock():
    lock = open(LOCK_FILE, 'w')
    try:
        # an exclusive, non-blocking file lock
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        print('Failed to acquire lock.')
        sys.exit(1)
    else:
        yield
    finally:
        # unlock it (to make testing easier)
        fcntl.flock(lock, fcntl.LOCK_UN)


def main(force):
    # Acquire an exclusive lock because clobbering the config file would be
    # very bad
    with acquire_lock():
        do_migration(force)


def import_config():
    '''Helper function to make mocking in tests easier.'''
    import config  # noqa
    return config


def do_migration(force, config_dir=CONFIG_DIR):
    source_config_file = path.join(config_dir, 'source-config.json')
    journalist_config_file = path.join(config_dir, 'journalist-config.json')

    try:
        config = import_config()
        HAS_CONFIG = True
        print('Python config imported.')
    except ImportError:
        config = None
        HAS_CONFIG = False
        print('Python config unable to be imported.')

    if path.exists(source_config_file) or path.exists(journalist_config_file):
        if force:
            print('JSON configs already exist, but --force was specified. '
                  'Overwriting config.')
        else:
            print('JSON config already exists. Exiting.')
            sys.exit(0)
    else:
        if not HAS_CONFIG:
            print('Python config file missing. Migrating empty values.')

    # First we attempt to collect the attributes

    try:
        id_pepper = config.SCRYPT_ID_PEPPER
        if not id_pepper:
            raise ValueError
    except (AttributeError, ValueError):
        id_pepper = None

    try:
        gpg_pepper = config.SCRYPT_GPG_PEPPER
        if not gpg_pepper:
            raise ValueError
    except (AttributeError, ValueError):
        gpg_pepper = None

    try:
        default_locale = config.DEFAULT_LOCALE
    except AttributeError:
        default_locale = None

    try:
        supported_locales = config.SUPPORTED_LOCALES
    except AttributeError:
        supported_locales = None

    if default_locale is not None and supported_locales is not None:
        i18n = {}
        if default_locale is not None:
            i18n['default_locale'] = default_locale
        if supported_locales is not None:
            i18n['supported_locales'] = supported_locales
    else:
        i18n = None

    try:
        scrypt_params = config.SCRYPT_PARAMS
    except AttributeError:
        scrypt_params = None

    try:
        journalist_key = config.JOURNALIST_KEY
    except AttributeError:
        journalist_key = None

    try:
        source_key = config.SourceInterfaceFlaskConfig.SECRET_KEY
    except AttributeError:
        source_key = None

    try:
        journalist_key = config.JournalistInterfaceFlaskConfig.SECRET_KEY
    except AttributeError:
        journalist_key = None

    try:
        custom_header_image = config.CUSTOM_HEADER_IMAGE
    except AttributeError:
        custom_header_image = None

    # Then we assemble them into a configs.
    # We allow a partial configs to be assembled in case of a partial
    # configuration of SecureDrop. Ansible will fill in the rest.

    source_config = {}
    journalist_config = {}

    if id_pepper is not None:
        source_config['scrypt_id_pepper'] = id_pepper
        journalist_config['scrypt_id_pepper'] = id_pepper

    if gpg_pepper is not None:
        source_config['scrypt_gpg_pepper'] = gpg_pepper
        journalist_config['scrypt_gpg_pepper'] = gpg_pepper

    if i18n is not None:
        source_config['i18n'] = i18n
        journalist_config['i18n'] = i18n

    if scrypt_params is not None:
        source_config['scrypt_params'] = scrypt_params
        journalist_config['scrypt_params'] = scrypt_params

    if source_key is not None:
        source_config['secret_key'] = source_key

    if journalist_key is not None:
        journalist_config['secret_key'] = journalist_key

    if custom_header_image is not None:
        source_config['custom_header_image'] = custom_header_image
        journalist_config['custom_header_image'] = custom_header_image

    safe_write_file(source_config, source_config_file)
    safe_write_file(journalist_config, journalist_config_file)


def safe_write_file(data, dest_file):
    temp_file = dest_file + '.tmp'

    if not path.exists(temp_file):
        # ensure file exists
        open(temp_file, 'w').close()
        # set safe permissions on it before we write secret values
        os.chmod(temp_file, 0o600)

    # Use a temp file to not clobber original in the event of an IO error
    with open(temp_file, 'w') as f:
        f.write(json.dumps(data))

    os.rename(temp_file, dest_file)


if __name__ == '__main__':
    parser = ArgumentParser(
        path.basename(__file__),
        description='Helper for migrating config from Python to JSON')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite the existing config.json')
    args = parser.parse_args()

    main(force=args.force)
