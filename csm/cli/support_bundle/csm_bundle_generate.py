#!/usr/bin/env python3

# CORTX-CSM: CORTX Management web and CLI interface.
# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

import os
import errno
import argparse
import sys
import pathlib
import shutil
sys.path.append(os.path.join(os.path.dirname(pathlib.Path(__file__)), '..', '..', '..'))
sys.path.append(os.path.join(os.path.dirname(pathlib.Path(os.path.realpath(__file__))), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(pathlib.Path(os.path.realpath(__file__))), '..', '..','..'))
from csm.core.blogic import const
from csm.common.payload import Yaml, Tar, Json
from cortx.utils.conf_store.conf_store import Conf
from cortx.utils.data.db.db_provider import (DataBaseProvider, GeneralConfig)
from csm.common.errors import CsmError
from cortx.utils.log import Log
from csm.core.services.alerts import AlertRepository
from cortx.utils.support_framework.log_filters import FilterLog

class CSMBundle:
    """
    ThiS Class generates the Support Bundle for Component CSM.
    Currently Included Files in CSM Support Bundle:-
    1) cortxcli.log -- Logs for CLI .
    2) csm_agent.log -- Logs for CSM Backend Agent.
    3) csm_setup.log -- Logs generated during setup for CSM Component.
    """

    @staticmethod
    async def init(command):
        """
        This method will generate bundle for CSM and include the logs in it.
        :param command: Csm_cli Command Object :type: command
        :return:
        """
        # Read Config to Fetch Log File Path
        csm_log_directory_path = Conf.get(const.CSM_GLOBAL_INDEX, "Log>log_path")
        uds_log_directory_path = Conf.get(const.CSM_GLOBAL_INDEX, "Log>uds_log_path")
        es_cluster_log_path = Conf.get(const.CSM_GLOBAL_INDEX, "Log>es_cluster_log_path")
        es_gc_log_path = Conf.get(const.CSM_GLOBAL_INDEX, "Log>es_gc_log_path")
        es_indexing_log_path = Conf.get(const.CSM_GLOBAL_INDEX, "Log>es_indexing_log_path")
        es_search_log_path = Conf.get(const.CSM_GLOBAL_INDEX, "Log>es_search_log_path")
        # Creates CSM Directory
        path = command.options.get("path")
        bundle_id = command.options.get("bundle_id")
        alerts_file_path = None
        component_name = command.options.get("component", "csm")
        component_data = {"csm": [csm_log_directory_path],
                          "uds": [uds_log_directory_path],
                          "elasticsearch": [es_cluster_log_path,
                                            es_gc_log_path,
                                            es_indexing_log_path,
                                            es_search_log_path]}
        if component_name == "alerts":
            alerts_filename = Conf.get(const.CSM_GLOBAL_INDEX,
                                       "SUPPORT_BUNDLE>alerts_filename")
            # Fetch alerts for support bundle.
            alerts_data = await CSMBundle.fetch_and_save_alerts()
            alerts_file_path = os.path.join(path, alerts_filename)
            obj_alert_json = Json(alerts_file_path)
            obj_alert_json.dump(alerts_data)
            component_data["alerts"] = [alerts_file_path]

        temp_path = os.path.join(path, component_name)
        os.makedirs(temp_path, exist_ok = True)
        # Generate Tar file for Logs Folder.
        tar_file_name = os.path.join(temp_path, f"{component_name}_{bundle_id}.tar.gz")
        if all(map(os.path.exists, component_data[component_name])):
            Tar(tar_file_name).dump(component_data[component_name])
        else:
            raise CsmError(rc = errno.ENOENT,
                           desc = f"Component log missing: {component_data[component_name]}")
        if alerts_file_path is not None:
            os.remove(alerts_file_path)

    @staticmethod
    async def fetch_and_save_alerts():
        """
        Fetches the alerts from es db and creates a json file
        :param command: Csm_cli Command Object :type: command
        :return: None
        """
        alerts =[]
        try:
            conf = GeneralConfig(Yaml(const.DATABASE_CONF).load())
            db = DataBaseProvider(conf)
            repo = AlertRepository(db)
            alerts = await repo.fetch_alert_for_support_bundle()
        except Exception as ex:
            Log.error(f"Error occured while fetching alerts: {ex}")
            alerts = [{"Error": "Internal error: Could not fetch alerts."}]
        return alerts

class GenerateCsmBundle:
    '''
    Csm support bundle generation class
    '''
    bundle_id = None
    target_path = None
    duration = None
    size_limit = None
    services = None
    binlogs = None
    coredumps = None
    stacktrace = None

    @staticmethod
    def generate_bundle(args):

        Conf.load(const.CONSUMER_INDEX, args[const.CONFIG_URL])
        log_path = Conf.get(const.CONSUMER_INDEX, const.CSM_LOG_PATH_KEY)
        csm_log_path = os.path.join(log_path, const.CSM_COMPONENT_NAME)
        GenerateCsmBundle.bundle_id = args[const.SB_BUNDLE_ID]
        GenerateCsmBundle.target_path = args [const.SB_TARGET]
        GenerateCsmBundle.duration = args[const.SB_DURATION]
        GenerateCsmBundle.size_limit = args[const.SB_SIZE_LIMIT]
        #NOTE: Not making use of services, binlogs, coredumps, stacktrace args.
        GenerateCsmBundle.services = args[const.SB_SERVICES]
        GenerateCsmBundle.binlogs = args[const.SB_BINLOGS]
        GenerateCsmBundle.coredumps = args[const.SB_COREDUMPS]
        GenerateCsmBundle.stacktrace = args[const.SB_STACKTRACE]
        target_path = os.path.join(GenerateCsmBundle.target_path, const.CSM_COMPONENT_NAME)
        os.makedirs(target_path,exist_ok=True)
        # Apply Time filter on CSM Logs Default: P5d
        csm_time_filtered_logs_dir = os.path.join(const.CSM_SETUP_LOG_DIR,
            f"{const.CSM_COMPONENT_NAME}_logs_time")
        GenerateCsmBundle.__clear_tmp_files(csm_time_filtered_logs_dir)
        os.makedirs(csm_time_filtered_logs_dir,exist_ok=True)
        FilterLog.limit_time(csm_log_path, csm_time_filtered_logs_dir,
            GenerateCsmBundle.duration, const.CSM_COMPONENT_NAME)
        # Create directory to keep filtered logs
        csm_size_filtered_logs_dir = os.path.join(const.CSM_SETUP_LOG_DIR,
            f"{const.CSM_COMPONENT_NAME}_logs")
        GenerateCsmBundle.__clear_tmp_files(csm_size_filtered_logs_dir)
        os.makedirs(csm_size_filtered_logs_dir,exist_ok=True)
        # Apply Size filter on Time Filtered CSM Logs
        FilterLog.limit_size(csm_time_filtered_logs_dir, csm_size_filtered_logs_dir,
            GenerateCsmBundle.size_limit, const.CSM_COMPONENT_NAME)
        # Create tar file name with bundle id
        tar_file_name = os.path.join(target_path, f"{GenerateCsmBundle.bundle_id}.tar.gz")
        # Tar Directory of filtered logs
        Tar(tar_file_name).dump([csm_size_filtered_logs_dir])
        GenerateCsmBundle.__clear_tmp_files(csm_size_filtered_logs_dir)
        GenerateCsmBundle.__clear_tmp_files(csm_time_filtered_logs_dir)

    @staticmethod
    def str2bool(value):
        if isinstance(value, bool):
            return value
        if value.lower() in ('true'):
            return True
        elif value.lower() in ('false'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')

    @staticmethod
    def __clear_tmp_files(path):
        """
        Clean temporary files created by the support bundle
        :param path: Directory path
        :return: None
        """
        shutil.rmtree(path, ignore_errors = True)

if __name__ == '__main__':
    from datetime import datetime
    parser = argparse.ArgumentParser(description='CSM Component Bundle Generate')
    parser.add_argument('-b','--bundle_id',
                    dest=const.SB_BUNDLE_ID,
                    help='Bundle-id',
                    default=f'SB_csm_{datetime.now().strftime("%d%m%Y_%H-%M-%S")}')
    parser.add_argument('-c','--config', dest=const.CONFIG_URL,
        help='Confstore URL eg:<type>://<path>')
    parser.add_argument('-s','--services', dest=const.SB_SERVICES,
        help='Run csm-service support-bundle', default='agent')
    parser.add_argument('-t','--target', dest=const.SB_TARGET,
        help='Target path to save support-bundle', default=const.CSM_SETUP_LOG_DIR)
    parser.add_argument('-d', '--duration', default='P5D', dest=const.SB_DURATION,
        help="Duration - duration for which log should be captured, Default - P5D")
    parser.add_argument('--size_limit', default='500MB', dest=const.SB_SIZE_LIMIT,
        help="Size Limit - Support Bundle size limit per node, Default - 500MB")
    parser.add_argument('--binlogs', type=GenerateCsmBundle.str2bool, default=False,
        dest=const.SB_BINLOGS, help="Include/Exclude Binary Logs, Default = False")
    parser.add_argument('--coredumps', type=GenerateCsmBundle.str2bool, default=False,
        dest=const.SB_COREDUMPS, help="Include/Exclude Coredumps, Default = False")
    parser.add_argument('--stacktrace', type=GenerateCsmBundle.str2bool, default=False,
        dest=const.SB_STACKTRACE, help="Include/Exclude stacktrace, Default = False")
    args = vars(parser.parse_args())

    GenerateCsmBundle.generate_bundle(args)
