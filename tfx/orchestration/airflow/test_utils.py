# Lint as: python3
# Copyright 2020 Google LLC. All Rights Reserved.
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
"""Common utility for testing airflow-based orchestrator."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import time

from typing import Text
from absl import logging
import docker

_MYSQL_POLLING_INTERVAL_SEC = 2
_MYSQL_POLLING_MAX_ATTEMPTS = 60
_MYSQL_PORT = '3306/tcp'


def create_mysql_container(container_name: Text) -> int:
  """Create a mysql docker container and returns port to it.

  A created mysql will have 'airflow' database and 'tfx' user without password.

  Args:
      container_name: A name of the new container.

  Returns:
      The new port number.

  Raises:
      RuntimeError: When mysql couldn't respond in pre-defined time limit or
                    failed to run initialization sqls.
  """

  client = docker.from_env()
  container = client.containers.run(
      'mysql:5.7',
      name=container_name,
      environment=['MYSQL_ROOT_PASSWORD=root'],
      ports={_MYSQL_PORT: None},
      detach=True)
  container.reload()  # required to get auto-assigned ports

  for _ in range(_MYSQL_POLLING_MAX_ATTEMPTS):
    logging.info('Waiting for mysqld container...')
    time.sleep(_MYSQL_POLLING_INTERVAL_SEC)
    exit_code, _ = container.exec_run(
        'mysql -uroot -proot -e "show databases;"')
    if exit_code == 0:
      break
  else:
    logging.error('Logs from mysql container:\n%s', container.logs())
    raise RuntimeError(
        'MySql could not started in %d seconds' %
        (_MYSQL_POLLING_INTERVAL_SEC * _MYSQL_POLLING_MAX_ATTEMPTS))

  create_db_sql = """
      CREATE USER 'tfx'@'%' IDENTIFIED BY '';
      GRANT ALL ON *.* TO 'tfx'@'%' WITH GRANT OPTION;
      FLUSH PRIVILEGES;
      SET GLOBAL explicit_defaults_for_timestamp = 1;
      CREATE DATABASE airflow;
  """
  exit_code, output_bytes = container.exec_run('mysql -uroot -proot -e "%s"' %
                                               create_db_sql)
  if exit_code != 0:
    output = output_bytes.decode('utf-8')
    logging.error('Failed to run sql for initialization:\n%s', output)
    logging.error('Logs from mysql container:\n%s', container.logs())
    raise RuntimeError('Failed to run initialization SQLs: {}'.format(output))

  return int(container.ports[_MYSQL_PORT][0]['HostPort'])


def delete_mysql_container(container_name: Text):
  """Delete a mysql docker container with name.

  Args:
      container_name: A name of the new container.
  """
  client = docker.from_env()
  container = client.containers.get(container_name)
  container.remove(force=True)
