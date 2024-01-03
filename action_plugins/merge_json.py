import os
import json
import textwrap

from ansible.plugins import action


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
            config.update(json.loads(result))

    def read_overrides_json(self, overrides_json, config):
        result = self._templar.template(overrides_json)
        config.update(result)

    def run(self, tmp=None, task_vars=None):

        super(ActionModule, self).run(tmp, task_vars)
        del tmp  # not used

        sources = self._task.args.get('sources', None)
        fact_name = self._task.args.get('fact_name', None)
        overrides_json = self._task.args.get('overrides_json', None)
        indent = self._task.args.get('indent', 4)

        merged_data = {}

        if not isinstance(sources, list):
            sources = [sources]

        for source in sources:
            self.read_config(source, merged_data)

        if overrides_json:
            self.read_overrides_json(overrides_json, merged_data)

        result = json.dumps(merged_data, ensure_ascii=False, indent=2)

        result = textwrap.indent(result, prefix=" " * indent)

        return dict(ansible_facts={fact_name: result})
