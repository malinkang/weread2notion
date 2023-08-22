"""
封装配置文件读取
"""
import os

import configparser

DEFAULT_CONFIG_FILE = 'default.ini'

def get_config_file():
    '''读取环境配置'''
    return os.environ.get('CONFIG_FILE', DEFAULT_CONFIG_FILE)

CONFIG_FILE = get_config_file()

def create_config(config_file=None):
    '''创建配置文件'''
    parser = configparser.ConfigParser()
    parser.read(config_file or CONFIG_FILE)
    return parser

CONFIG = create_config()
