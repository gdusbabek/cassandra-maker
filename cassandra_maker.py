#!/usr/bin/python

# Copyright 2010 Gary Dusbabek. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are
# permitted provided that the following conditions are met:
# 
#    1. Redistributions of source code must retain the above copyright notice, this list of
#       conditions and the following disclaimer.
# 
#    2. Redistributions in binary form must reproduce the above copyright notice, this list
#       of conditions and the following disclaimer in the documentation and/or other materials
#       provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY GARY DUSBABEK ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL GARY DUSBABEK OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# 
# The views and conclusions contained in the software and documentation are those of the
# authors and should not be interpreted as representing official policies, either expressed
# or implied, of Gary Dusbabek.

import sys, os, stat
import shutil
import yaml

def rewrite_yaml(yaml_path, config_dst, octet, token):
    """rewrites the yaml file according to your configuration"""
    y = yaml.load(open(yaml_path))
    # You'll want to hack this part up to sub in values that mean something to you.
    y['auto_bootstrap'] = True
    y['hinted_handoff_enabled'] = False
    y['concurrent_writes'] = 4
    y['concurrent_reads'] = 4
    y['listen_address'] = '127.0.0.' + str(octet)
    y['rpc_address'] = y['listen_address']
    y['data_file_directories'] = [config_dst + '/data_' + octet + '/data']
    y['commitlog_directory'] = [config_dst + '/data_' + octet + '/commitlog']
    y['saved_caches_directory'] = [config_dst + '/data_' + octet + '/savedcaches']
    y['keyspaces'][0]['replication_factor'] = 2
    y['initial_token'] = int(token)
    open(yaml_path, 'w').write(yaml.dump(y))

def rewrite_env(env_path, octet):
    """rewrites any lines that are host/port specific."""
    dupe = env_path + '~'
    os.rename(env_path, dupe)
    src = open(dupe, 'r')
    dst = open(env_path, 'w')
    for line in src:
        # JMX_PORT=
        if line.startswith('JMX_PORT='):
            dst.write('#' + line)
            dst.write('JMX_PORT="808' + octet + '"')
        else:
            dst.write(line)
            
    # let's add a few things to jvm opts
    dst.write('\n')
    dst.write('# these options were added by cassandra_maker.py\n')
    dst.write('JMV_OPTS="$JVM_OPTS -Djava.rmi.server.useLocalHostname=false"\n')
    dst.write('JMV_OPTS="$JVM_OPTS -Djava.rmi.server.hostname=127.0.0.' + octet +'"\n')
    
    src.close()
    dst.close()
    os.remove(dupe)
    os.chmod(env_path, 493)

def write_in_sh(sh_path, cass_home, cass_config, octet):
    """writes the cassandra.in.sh file"""
    f = open(sh_path, 'w')
    f.write('CASSANDRA_HOME=' + cass_home + '\n')
    f.write('CASSANDRA_CONF=' + cass_config + '\n')
    f.write('cassandra_bin=$CASSANDRA_HOME/build/classes\n')
    f.write('if [ "x$CASSANDRA_HOME" = "x" ]; then\n')
    f.write('    CASSANDRA_HOME=`dirname $0`/..\n')
    f.write('fi\n')
    f.write('if [ "x$CASSANDRA_CONF" = "x" ]; then\n')
    f.write('    CASSANDRA_CONF=$CASSANDRA_HOME/conf\n')
    f.write('fi\n')
    f.write('CLASSPATH=$CASSANDRA_CONF:$cassandra_bin\n')
    f.write('for jar in $CASSANDRA_HOME/lib/*.jar; do\n')
    f.write('    CLASSPATH=$CLASSPATH:$jar\n')
    f.write('done\n')
    f.write('echo using custom include for config ' + octet)
    f.close()
    os.chmod(sh_path, 493)
    

def write_command(cmd_file, cass_home, sh_path):
    # OS X only.
    f = open(cmd_file, 'w')
    f.write('#!/bin/sh\n')
    f.write('CASSANDRA_INCLUDE=' + sh_path + '\n')
    f.write('export CASSANDRA_INCLUDE\n')
    f.write('cd ' + cass_home + '\n')
    f.write('bin/cassandra -f\n')
    f.close()
    os.chmod(cmd_file, 493)

def usage(exit_code):
    print 'usage:'
    print 'cassandra_maker.py <cassandra source home> <configurations destination> <config names>...'
    print '<config names> is a space delimted list of integers that will be used to identify configurations and hosts.'
    print 'so if you specify \'1 2 3\', three confgs will be made, one each for 127.0.0.1, 127.0.0.2, 127.0.0.3.'
    sys.exit(exit_code)
    
def main(argv=None):
    if argv is None:
        argv = sys.argv
        
    config_src = argv[1]
    config_dst = argv[2]
    
    if len(argv) < 3:
        usage(1)
        
    startup_ext = '.command'

    node_count = len(argv[3:])
    tokens = [2**127 / node_count * x for x in xrange(node_count)]

    for cfg_name, token in zip(argv[3:], tokens):
        # make the conf dir.
        new_conf_path = os.path.join(config_dst, 'conf_' + cfg_name)
        print 'making config at ' + new_conf_path
        try:
            os.makedirs(new_conf_path)
        except OSError:
            pass
        
        # make the data dir
        try:
            os.mkdir(os.path.join(config_dst, 'data_' + cfg_name))
        except OSError:
            pass
    
        # copy all the files from config_src,
        conf_dir = os.path.join(config_src, 'conf')
        print 'copying config files from ' + conf_dir
        for f in os.listdir(conf_dir):
            if f.startswith('.'): continue
            shutil.copyfile(os.path.join(conf_dir, f), os.path.join(new_conf_path, f))
        print 'copied config files ' + cfg_name
    
        yaml_path = os.path.join(new_conf_path, 'cassandra.yaml')
        rewrite_yaml(yaml_path, config_dst, cfg_name, token)
        print 'rewrote ' + yaml_path
        
        env_path = os.path.join(new_conf_path, 'cassandra-env.sh')
        rewrite_env(env_path, cfg_name)
        print 'rewrote ' + env_path
        
        sh_path = os.path.join(config_dst, cfg_name + '.in.sh')
        write_in_sh(sh_path, config_src, new_conf_path, cfg_name)
        print 'wrote ' + cfg_name + '.in.sh'
        
        cmd_file = os.path.join(config_dst, 'startup_' + cfg_name + startup_ext)
        write_command(cmd_file, config_src, sh_path)
        print 'wrote ' + cmd_file
        
        

if __name__ == '__main__':
    main(sys.argv)