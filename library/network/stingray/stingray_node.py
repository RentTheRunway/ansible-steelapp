#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import requests

DOCUMENTATION = """
---
module: stingray_node
version_added: 1.8.2
short_description: manage nodes in stingray traffic managers
description:
    - Manage nodes in a Stingray Traffic Managers
author: Kim Nørgaard
options:
    name:
        description:
            - Name of node to work on
        required: true
        default: null
        aliases: ['node']
    pool:
        description:
            - Name of pool to work on
        required: true
        default: null
    state:
        description:
            - Operation to perform on node
        required: false
        default: 'present'
        choices: ['present', 'absent']
    lb_state:
        description:
            - State to set in load balancer
        required: false
        choices: ['active', 'disabled', 'draining']
    weight:
        description:
            - Set the weight of the node
        required: false
    priority:
        description:
            - Set the priority of the node
        required: false
    server:
        description:
            - Server to connect to (without URI scheme or port)
        required: true
        default: null
    port:
        description:
            - Port used to connect to server
        required: false
        default: 9070
    timeout:
        description:
            - Timeout for HTTP connections
        required: false
        default: 3
    user:
        description:
            - Username used for authentication
        required: true
        default: null
    password:
        description:
            - Password used for authentication
        required: true
        default: null
"""
# TODO: examples

class StingrayNode(object):
    def __init__(self, module, server, port, timeout, user, password, pool,
                 node, weight, priority, lb_state):
        self.module           = module
        self.server           = server
        self.port             = port
        self.timeout          = timeout
        self.user             = user
        self.password         = password
        self.pool             = pool
        self.node             = node
        self.desired_weight   = weight
        self.desired_priority = priority
        self.desired_lb_state = lb_state
        self.msg              = ''
        self.changed          = False

        self._url = 'https://{0}:{1}/api/tm/3.0/config/active/pools/{2}'.format(server, port, pool)
        self._jsontype = {'content-type': 'application/json'}

        self._client = requests.Session()
        self._client.auth = (user, password)
        self._client.verify = False

        try:
            response = self._client.get(self._url, timeout=self.timeout)
        except requests.exceptions.ConnectionError as e:
            self.module.fail_json(msg=
                    "Unable to connect to {0}: {1}".format(self._url, str(e)))

        if response.status_code == 404:
            self.module.fail_json(msg="Pool {0} not found".format(self.pool))

        try:
            self.pool_data = json.loads(response.text)
        except Exception as e:
            self.module.fail_json(msg=str(e))

    def _nodes(self):
        return self.pool_data['properties']['basic']['nodes_table']

    def _node_exists(self):
        return bool(self._get_current_node())

    def _get_current_node(self):
        return [n for n in self._nodes() if n['node'] == self.node]

    def _has_state(self, state):
        return bool([n for n in self._nodes()
            if n['node'] == self.node and n['state'] == state])

    def set_nodes(self, nodes):
            pool_data = {
                    'properties': {
                        'basic': {
                            'nodes_table': nodes
                        }
                    }
            }

            return self._client.put(self._url, data = json.dumps(pool_data),
                                    headers = self._jsontype)

    def set_absent(self):
        self.changed = False
        changes = {
                'node': self.node,
                'pool': self.pool
        }

        if self._node_exists():
            self.changed = True
            changes['action'] = 'remove_node'
            self.msg = changes

            if self.module.check_mode:
                return

            new_nodes = [n for n in self._nodes() if n['node'] != self.node]
            response = self.set_nodes(new_nodes)

            if response.status_code == 200:
                self.pool_data = json.loads(response.text)
            else:
                changes['error'] = "HTTP {2}".format(response.status_code)
                self.module.fail_json(msg=changes)
        else:
            self.changed = False
            self.msg = changes

    def set_present(self):
        self.changed = False
        changes = {
                'node': self.node,
                'pool': self.pool
        }

        if not self._node_exists():
            changes['action'] = 'add_node'
            self.msg = changes
            self.changed = True

            if self.module.check_mode:
                return

            new_nodes = self._nodes()+[
                    {
                        'node'    : self.node,
                        'state'   : self.desired_lb_state or 'active',
                        'weight'  : self.desired_weight or 1,
                        'priority': self.desired_priority or 1,
                    }]
            response = self.set_nodes(new_nodes)

            if response.status_code == 200:
                self.pool_data = json.loads(response.text)
            else:
                changes['error'] = "HTTP {2}".format(response.status_code)
                self.module.fail_json(msg=changes)
        else:
            current_node = self._get_current_node()[0]

            if self.desired_lb_state and self.desired_lb_state != current_node['state']:
                changes['state'] = { 'before': current_node['state'], 'after': self.desired_lb_state }
                current_node['state'] = self.desired_lb_state
                self.changed = True

            if self.desired_weight and self.desired_weight != current_node['weight']:
                changes['weight'] = { 'before': current_node['weight'], 'after': self.desired_weight }
                current_node['weight'] = self.desired_weight
                self.changed = True

            if self.desired_priority and self.desired_priority != current_node['priority']:
                changes['priority'] = { 'before': current_node['priority'], 'after': self.desired_priority }
                current_node['priority'] = self.desired_priority
                self.changed = True

            if self.changed:
                self.msg = changes
                if self.module.check_mode:
                    return

                new_nodes = [n for n in self._nodes() if n['node'] != self.node]
                new_nodes = new_nodes+[current_node]

                response = self.set_nodes(new_nodes)

                if response.status_code == 200:
                    self.pool_data = json.loads(response.text)
                else:
                    changes['error'] = "HTTP {2}".format(response.status_code)
                    self.module.fail_json(msg=changes)
            else:
                self.msg = changes


def main():
    module = AnsibleModule(
            argument_spec = dict(
                name      = dict(required=True, aliases=['node']),
                pool      = dict(required=True),
                state     = dict(choices=['absent','present'],
                                 required=False,
                                 default='present'),
                lb_state  = dict(choices=['active','disabled','draining'],
                                 required=False),
                weight    = dict(required=False),
                priority  = dict(required=False),
                server    = dict(required=True),
                port      = dict(default=9070, required=False),
                timeout   = dict(default=3, required=False),
                user      = dict(required=True),
                password  = dict(required=True),
            ),
            supports_check_mode = True,
    )

    state      = module.params['state']
    server     = module.params['server']
    port       = module.params['port']
    timeout    = module.params['timeout']
    user       = module.params['user']
    password   = module.params['password']
    pool       = module.params['pool']
    node       = module.params['name']
    weight     = module.params['weight']
    priority   = module.params['priority']
    lb_state   = module.params['lb_state']

    stingray_node = StingrayNode(module, server, port, timeout, user, password,
                                 pool, node, weight, priority, lb_state)

    try:
        if state == 'present':
            stingray_node.set_present()
        elif state == 'absent':
            stingray_node.set_absent()
        else:
            module.fail_json(msg="Unsupported state: {0}".format(state))

        module.exit_json(changed=stingray_node.changed, msg=stingray_node.msg,
                         data=stingray_node.pool_data)
    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
