#!/usr/bin/env python

# Copyright 2015 Sam Yaple
# Copyright 2017 99Cloud Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import collections
import os

from ansible.plugins import action
from io import StringIO

from oslo_config import iniparser

_ORPHAN_SECTION = 'TEMPORARY_ORPHAN_VARIABLE_SECTION'

DOCUMENTATION = '''
---
module: merge_configs
short_description: Merge ini-style configs
description:
     - ConfigParser is used to merge several ini-style configs into one
options:
  dest:
    description:
      - The destination file name
    required: True
    type: str
  sources:
    description:
      - A list of files on the destination node to merge together
    default: None
    required: True
    type: str
  whitespace:
    description:
      - Whether whitespace characters should be used around equal signs
    default: True
    required: False
    type: bool
author: Sam Yaple
'''

EXAMPLES = '''
Merge multiple configs:

- hosts: database
  tasks:
    - name: Merge configs
      merge_configs:
        sources:
          - "/tmp/config_1.cnf"
          - "/tmp/config_2.cnf"
          - "/tmp/config_3.cnf"
        dest:
          - "/etc/mysql/my.cnf"
'''


class OverrideConfigParser(iniparser.BaseParser):

    def __init__(self, whitespace=True):
        self._cur_sections = collections.OrderedDict()
        self._sections = collections.OrderedDict()
        self._cur_section = None
        self._whitespace = ' ' if whitespace else ''

    def assignment(self, key, value):
        if self._cur_section is None:
            self.new_section(_ORPHAN_SECTION)
        cur_value = self._cur_section.get(key)
        if len(value) == 1 and value[0] == '':
            value = []
        if not cur_value:
            self._cur_section[key] = [value]
        else:
            self._cur_section[key].append(value)

    def parse(self, lineiter):
        self._cur_sections = collections.OrderedDict()
        self._cur_section = None
        super(OverrideConfigParser, self).parse(lineiter)

        # merge _cur_sections into _sections
        for section, values in self._cur_sections.items():
            if section not in self._sections:
                self._sections[section] = collections.OrderedDict()
            for key, value in values.items():
                self._sections[section][key] = value

    def new_section(self, section):
        cur_section = self._cur_sections.get(section)
        if not cur_section:
            cur_section = collections.OrderedDict()
            self._cur_sections[section] = cur_section
        self._cur_section = cur_section
        return cur_section

    def write(self, fp, indent=None):
        indent = ' ' * indent
        def write_key_value(key, values):
            for v in values:
                if not v:
                    fp.write('{indent}{key}{ws}=\n'.format(
                        indent=indent, key=key, ws=self._whitespace))
                for index, value in enumerate(v):
                    if index == 0:
                        fp.write('{indent}{key}{ws}={ws}{value}\n'.format(
                            indent=indent,
                            key=key,
                            ws=self._whitespace,
                            value=value))
                    else:
                        # We want additional values to be written out under the
                        # first value with the same indentation, like this:
                        # key = value1
                        #       value2
                        indent_size = len(key) + len(self._whitespace) * 2 + 1
                        ws_indent = ' ' * indent_size
                        fp.write('{indent}{ws_indent}{value}\n'.format(
                            indent=indent,
                            ws_indent=ws_indent,
                            value=value))

        def write_section(section):
            for key, values in section.items():
                write_key_value(key, values)

        for section in self._sections:
            if section != _ORPHAN_SECTION:
                fp.write('{}[{}]\n'.format(indent, section))
            write_section(self._sections[section])
            fp.write('\n')


class ActionModule(action.ActionBase):

    TRANSFERS_FILES = True

    def read_config(self, source, config):
        # Only use config if present
        if os.access(source, os.R_OK):
            with open(source, 'r') as f:
                template_data = f.read()

            # set search path to mimic 'template' module behavior
            searchpath = [
                self._loader._basedir,
                os.path.join(self._loader._basedir, 'templates'),
                os.path.dirname(source),
            ]
            self._templar.environment.loader.searchpath = searchpath

            result = self._templar.template(template_data)
            fakefile = StringIO(result)
            config.parse(fakefile)
            fakefile.close()

    def read_overrides_conf(self, overrides_conf, config):
        result = self._templar.template(overrides_conf)
        fakefile = StringIO(result)
        config.parse(fakefile)
        fakefile.close()

    def run(self, tmp=None, task_vars=None):

        super(ActionModule, self).run(tmp, task_vars)
        del tmp  # not used

        sources = self._task.args.get('sources', None)
        fact_name = self._task.args.get('fact_name', None)
        overrides_conf = self._task.args.get('overrides_conf', None)
        indent = self._task.args.get('indent', 4)

        if not isinstance(sources, list):
            sources = [sources]

        config = OverrideConfigParser(
            whitespace=self._task.args.get('whitespace', True))

        for source in sources:
            self.read_config(source, config)

        self.read_overrides_conf(overrides_conf, config)

        fakefile = StringIO()
        config.write(fakefile, indent=indent)
        full_source = fakefile.getvalue()
        fakefile.close()

        return dict(ansible_facts={fact_name: full_source})
