# Copyright (c) 2015 EMC Corporation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from __future__ import unicode_literals

import logging

from storops.unity.enums import NFSShareDefaultAccessEnum, NFSTypeEnum, \
    NFSShareSecurityEnum
import storops.unity.resource.filesystem
import storops.unity.resource.snap
from storops.unity.resource import UnityResource, UnityResourceList
import storops.unity.resource.host

__author__ = 'Jay Xu'

LOG = logging.getLogger(__name__)


class UnityNfsHostConfig(object):
    def __init__(self, root=None, ro=None, rw=None, no_access=None,
                 nfs_share=None):
        if nfs_share is not None:
            root = nfs_share.root_access_hosts
            ro = nfs_share.read_only_hosts
            rw = nfs_share.read_write_hosts
            no_access = nfs_share.no_access_hosts

        self.root = root
        self.ro = ro
        self.rw = rw
        self.no_access = no_access

    @classmethod
    def _add(cls, left, right):
        if left is None:
            ret = right
        elif right is None:
            ret = left
        else:
            ret = left
            for r in right:
                if r not in left:
                    ret.append(r)
        return ret

    @classmethod
    def _remove(cls, left, right):
        if left is None:
            ret = None
        elif right is None:
            ret = left
        else:
            ret = []
            for l in left:
                if l not in right:
                    ret.append(l)
        return ret

    def allow_root(self, *hosts):
        self.remove_access(*hosts)
        self.root = self._add(self.root, hosts)
        return self

    def allow_ro(self, *hosts):
        self.remove_access(*hosts)
        self.ro = self._add(self.ro, hosts)
        self.root = self._add(self.root, hosts)
        return self

    def allow_rw(self, *hosts):
        self.remove_access(*hosts)
        self.rw = self._add(self.rw, hosts)
        self.root = self._add(self.root, hosts)
        return self

    def deny_access(self, *hosts):
        self.remove_access(*hosts)
        self.no_access = self._add(self.no_access, hosts)
        return self

    def remove_access(self, *hosts):
        self.rw = self._remove(self.rw, hosts)
        self.ro = self._remove(self.ro, hosts)
        self.no_access = self._remove(self.no_access, hosts)
        self.root = self._remove(self.root, hosts)
        return self

    def clear_all(self):
        self.rw = []
        self.ro = []
        self.no_access = []
        self.root = []
        return self


class UnityNfsShare(UnityResource):
    @classmethod
    def create(cls, cli, name, fs, path=None, share_access=None):
        fs_clz = storops.unity.resource.filesystem.UnityFileSystem
        fs = fs_clz.get(cli, fs).verify()
        NFSShareDefaultAccessEnum.verify(share_access)
        sr = fs.storage_resource

        if path is None:
            path = '/'

        share_param = cli.make_body(defaultAccess=share_access)
        param = cli.make_body(name=name, path=path,
                              nfsShareParameters=share_param)
        resp = sr.modify_fs(nfsShareCreate=[param])
        resp.raise_if_err()
        return UnityNfsShareList(cli=cli, name=name).first_item

    @classmethod
    def create_from_snap(cls, cli, snap, name, path=None, is_read_only=None,
                         default_access=None):
        snap_clz = storops.unity.resource.snap.UnitySnap
        snap = snap_clz.get(cli, snap)
        NFSShareDefaultAccessEnum.verify(default_access)

        if path is None:
            path = '/'

        resp = cli.post(cls().resource_class,
                        snap=snap,
                        path=path,
                        name=name,
                        isReadOnly=is_read_only,
                        defaultAccess=default_access)
        resp.raise_if_err()
        return cls(_id=resp.resource_id, cli=cli)

    def remove(self, async=False):
        if self.type == NFSTypeEnum.NFS_SNAPSHOT:
            resp = super(UnityNfsShare, self).remove(async=async)
        else:
            fs = self.filesystem.verify()
            sr = fs.storage_resource
            param = self._cli.make_body(nfsShare=self)
            resp = sr.modify_fs(async=async, nfsShareDelete=[param])
        resp.raise_if_err()
        return resp

    def _get_hosts(self, hosts, force_create_host=False):
        if not isinstance(hosts, (tuple, list, set, UnityResourceList)):
            hosts = [hosts]
        host_clz = storops.unity.resource.host.UnityHost
        ret = []
        for item in hosts:
            host = host_clz.get_host(self._cli, item, force_create_host)
            if host is not None:
                ret.append(host)
        return ret

    @property
    def host_config(self):
        return UnityNfsHostConfig(nfs_share=self)

    def allow_root_access(self, hosts, force_create_host=False):
        hosts = self._get_hosts(hosts, force_create_host)
        config = self.host_config.allow_root(*hosts)
        return self.modify(host_config=config)

    def allow_read_only_access(self, hosts, force_create_host=False):
        hosts = self._get_hosts(hosts, force_create_host)
        config = self.host_config.allow_ro(*hosts)
        return self.modify(host_config=config)

    def allow_read_write_access(self, hosts, force_create_host=False):
        hosts = self._get_hosts(hosts, force_create_host)
        config = self.host_config.allow_rw(*hosts)
        return self.modify(host_config=config)

    def deny_access(self, hosts, force_create_host=False):
        hosts = self._get_hosts(hosts, force_create_host)
        config = self.host_config.deny_access(*hosts)
        return self.modify(host_config=config)

    def remove_access(self, hosts):
        hosts = self._get_hosts(hosts)
        config = self.host_config.remove_access(*hosts)
        return self.modify(host_config=config)

    def clear_access(self):
        config = self.host_config.clear_all()
        return self.modify(host_config=config)

    def modify(self,
               default_access=None,
               min_security=None,
               no_access_hosts=None,
               read_only_hosts=None,
               read_write_hosts=None,
               root_access_hosts=None,
               host_config=None):
        if host_config is not None:
            no_access_hosts = host_config.no_access
            root_access_hosts = host_config.root
            read_only_hosts = host_config.ro
            read_write_hosts = host_config.rw

        NFSShareDefaultAccessEnum.verify(default_access)
        NFSShareSecurityEnum.verify(min_security)
        clz = storops.unity.resource.host.UnityHostList
        no_access_hosts = clz.get_list(self._cli, no_access_hosts)
        read_only_hosts = clz.get_list(self._cli, read_only_hosts)
        read_write_hosts = clz.get_list(self._cli, read_write_hosts)
        root_access_hosts = clz.get_list(self._cli, root_access_hosts)

        fs = self.filesystem
        if fs is None:
            raise ValueError(
                'filesystem for share {} not found.'.format(self.name))
        sr = fs.storage_resource
        if sr is None:
            raise ValueError('storage resource for filesystem {}, '
                             'share {} not found.'.format(self.name, fs.name))

        nfs_share_param = self._cli.make_body(
            allow_empty=True,
            defaultAccess=default_access,
            minSecurity=min_security,
            noAccessHosts=no_access_hosts,
            readOnlyHosts=read_only_hosts,
            readWriteHosts=read_write_hosts,
            rootAccessHosts=root_access_hosts)
        nfs_share = self._cli.make_body(
            allow_empty=True,
            nfsShare=self,
            nfsShareParameters=nfs_share_param)
        param = self._cli.make_body(
            allow_empty=True,
            nfsShareModify=[nfs_share])
        resp = sr.modify_fs(**param)
        resp.raise_if_err()
        return resp


class UnityNfsShareList(UnityResourceList):
    @classmethod
    def get_resource_class(cls):
        return UnityNfsShare
