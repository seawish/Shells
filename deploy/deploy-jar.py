#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# 脚本用途：上传并部署SpringBoot项目:
# 1. kill 旧的jar进程
# 2. 备份旧文件到jar所在目录下的子目录（目录名：yymmdd），删除nohup文件。
#   备份的文件包括：logs, jar文件, application*
# 3. 上传新的jar，目录下所有文件都会被上传。
# 4. 运行jar包
#
# 注意事项：
# 
# 在host_dic中添加部署节点。
# 需要先安装paramiko: pip install paramiko
# 将需要上传的文件放到同一目录, 执行命令(参数为待上传文件的父目录、服务器文件存储目录、待运行的jar):
# 运行命令： python deploy-jar.py local_dir remote_dir jar_name

import paramiko
import time
from multiprocessing import Pool
import os
import sys

# remote host的ssh信息
# host: [username, password, port, server-ip]
host_dic = {
    '139.129.1.1': ['root', 'password', 22, "172.18.211.105"],
    '139.129.1.2': ['root', 'password', 22, "172.18.211.106"]
}

def run_cmd(ssh_client, cmd):
    """
    运行单条命令
    :param ssh_client:
    :param cmd:
    :return:
    """
    # bash -l -c解释：-l（login）表示bash作为一个login shell；-c(command)表示执行后面字符串内的命令，这样执行的脚本，可以获取到/etc/profile里的全局变量，包括我们搜索命令的目录PATH
    print("执行命令: " + cmd)
    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    error_msg = stderr.read()
    if error_msg:
        print("run_cmd error: " + error_msg)
    result = stdout.read()
    print("运行结果: " + result)
    return result


def mkdirs(ssh_client, sftp, dir):
    """
    创建目录, 如果父目录没有创建, 则创建父目录
    :param ssh_client:
    :param sftp:
    :param dir 远程主机的目录
    :return:
    """
    try:
        sftp.stat(dir)
        print("directory exist: " + dir)
    except IOError:
        print("directory not exist, create dir")
        cmd = "mkdir -p " + dir
        run_cmd(ssh_client, cmd)


def sftp_upload(ssh_client, sftp, local_path, remote_path):
    """
    上传本地文件夹下文件到服务器
    :param ssh_client:
    :param sftp:
    :param local_path: 本地文件/文件夹路径, 可以为绝对路径也可以为相对路径
    :param remote_path: 远程文件存储路径
    :return:
    """
    try:
        if os.path.isdir(local_path):  # 判断本地参数是目录还是文件
            mkdirs(ssh_client, sftp, remote_path)

            for f in os.listdir(local_path):  # 遍历本地目录
                local_path_tmp = os.path.join(local_path, f)
                # 远程服务器为linux
                remote_path_tmp = os.path.join(remote_path, f).replace("\\", "/")
                sftp_upload(ssh_client, sftp, local_path_tmp, remote_path_tmp)
        else:
            print("sftp_upload local:  " + local_path)
            print("sftp_upload remote:  " + remote_path)
            sftp.put(local_path, remote_path)  # 上传文件
    except Exception as e:
        print("upload exception:", e)


def kill_jar(ssh_client, jar_name):
    """
    kill正在运行的nziot-api进程
    :return:
    """
    # grep_pid_cmd = "ps -A -o pid,command | grep " + jar_name+ " | grep -v grep | cut -d" " -f 1"
    grep_pid_cmd = "ps -ef | grep "  + jar_name+ " | grep -v grep | awk '{print $2}'"

    pid_str = run_cmd(ssh_client, grep_pid_cmd)
    if pid_str:
        pid_list = pid_str.strip().splitlines()
        for pid in pid_list:
            print("正在kill进程，进程id：" + pid)
            kill_pid_cmd = "kill " + pid
            run_cmd(ssh_client, kill_pid_cmd)
    else:
        print("没有进程在运行。")


def back_old_jar(ssh_client, sftp,  parent_dir):
    """
    将旧的jar文件移动到新的文件夹，文件夹以日期命名：yymmdd
    :param ssh_client:
    :param parent_dir: 模块父目录
    """
    # back_dir = parent_dir + "/" + time.strftime("%Y%m%d");
    back_dir = os.path.join(parent_dir, time.strftime("%Y%m%d"))
    # 创建目录
    mkdirs(ssh_client, sftp, back_dir)
    # 备份旧文件
    old_files = parent_dir + "/nziot* "  + parent_dir + "/application* " + parent_dir + "/logs"
    mv_cmd = "mv " + old_files + " -t " + back_dir
    run_cmd(ssh_client, mv_cmd)
    # 删除nohup
    # nohup_path = parent_dir + "/nohup*"
    nohup_path = os.path.join(parent_dir, "nohup*")

    rm_cmd = "rm -f " + nohup_path
    print("删除文件: " + nohup_path)
    run_cmd(ssh_client, rm_cmd)

def run_jar(ssh_client, parent_dir, jar_name, config_name):
    """
    异步运行nziot-iot进程
    :param ssh_client:
    :param jar_path:
    :return:
    """
    jar_path = os.path.join(parent_dir, jar_name)
    config_path = os.path.join(parent_dir, config_name)
    nohup_path = os.path.join(parent_dir, "nohup.out")

    # echo -n 不换行输出
    echo_cmd = "bash -lc 'echo -n $JAVA_HOME/bin/java -jar " + jar_path + "'"
    # echo_cmd = "echo -n $JAVA_HOME/bin/java -jar " + jar_name
    # echo_cmd = "echo -n $JAVA_HOME/bin/java -jar " + jar_name  
    jar_cmd = run_cmd(ssh_client, echo_cmd)

    # 进入工作目录
    # nohup_cmd = "nohup /usr/java/jdk1.8.0_151/bin/java -jar " + jar_path  + " &> " +  nohup_path + " &"
    cd_cmd = "cd " + parent_dir
    nohup_cmd = "nohup " + jar_cmd + " &> " +  nohup_path + " &"
    # nohup /usr/java/jdk1.8.0_151/bin/java -jar /root/nziot/nziot_api/nziot_api-0.0.6.jar &> /root/nziot/nziot_api/nohup.out &
    # print nohup_cmd
    run_cmd(ssh_client, cd_cmd + ";" + nohup_cmd)

def replace_line(ssh_client, cfg_path, src_str, dst_str):
    """
    将cfg_path文件中的字符串src_str替换为dst_str, 整行替换
    """
    sed_cmd =  "sed -ie 's/%s.*/%s/ ' %s" % (src_str, dst_str, cfg_path)
    run_cmd(ssh_client, sed_cmd)

    grep_cmd = "grep '%s.*' %s" % (dst_str, cfg_path)
    grep_res = run_cmd(ssh_client, grep_cmd)

    # if(grep_res.strip('\n') == tartget_str):
    #     print("在文件 %s 替换 %s 为 %s 成功" % (cfg_path, src_str, dst_str))
    #     return True
    # else:
    #     print("在文件 %s 替换 %s 为 %s 失败, 配置文件中内容：%s" % (cfg_path, src_str, dst_str, grep_res.strip('\n')))
    #     return False

def config(ssh_client, cfg_path, server_address):
    """
    设置配置文件中的host
    """
     # 找到匹配的行
    print("在 %s 中配置server.address: %s" % (cfg_path, server_address))

    # 设置id
    src_str = "server.address="
    dst_str = src_str + server_address
    replace_line(ssh_client, cfg_path, src_str, dst_str)

    grep_cmd = "grep '%s.*' %s" % (src_str, cfg_path)
    grep_res = run_cmd(ssh_client, grep_cmd)

    if(grep_res.strip('\n') == dst_str):
        print("配置服务器地址为 %s 成功" % server_address)
        return True
    else:
        print("配置服务器地址为 %s 失败, 配置文件中内容：%s" % (server_address, grep_res.strip('\n')))
        return False

def tail_file(ssh_client, file_path, line_num):
    """
    查看文件尾部n行
    :param file_path: 文件路径
    :param line_num: 文件尾部行数
    :return:
    """
    print("查看文件 %s 尾部 %s 行。" % (file_path, line_num))
    tail_cmd = "tail -n100 " + file_path
    run_cmd(ssh_client, tail_cmd)

def deploy(host, host_info, local_dir, remote_dir, jar_name):
    """
    部署nziot-api
    :param host:
    :param port:
    :param username:
    :param password:
    :return:
    """
    print("----------%s----------" % host)
    username, password, port, server_address = host_info

    ssh_client = paramiko.SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh_client.connect(host, port, username=username, password=password, timeout=5)

    sf = paramiko.Transport((host, port))
    sf.connect(username=username, password=password)
    sftp = paramiko.SFTPClient.from_transport(sf)

    # 关闭api进程
    kill_jar(ssh_client, jar_name)

    # 备份旧文件
    back_old_jar(ssh_client, sftp,  remote_dir)

    # 上传文件
    sftp_upload(ssh_client, sftp, local_dir, remote_dir)

    # 配置服务器地址
    cfg_name = "application-dev.properties"
    cfg_path = remote_dir + "/" + cfg_name
    config(ssh_client, cfg_path, server_address)

    # 运行新进程
    remote_dir = remote_dir.replace("\\", "/")
    run_jar(ssh_client, remote_dir, jar_name, cfg_name)

    # 查看nohup文件
    nohup_path = remote_dir + "/nohup.out"
    time.sleep(4) #睡眠4秒
    tail_file(ssh_client, nohup_path, 100)

    sf.close()
    ssh_client.close()


if __name__ == "__main__":
    """
    sys.argv[1]: local_dir
    sys.argv[2]: remote_dir
    sys.argv[3]: jar_name
    """
    local_dir = sys.argv[1]
    remote_dir = sys.argv[2]
    jar_name = sys.argv[3]
   
    print("local_dir: " + local_dir)
    print("remote_dir: " + remote_dir)

    pool = Pool(3)
    res_list = []

    for host, host_info in host_dic.items():
        deploy(host, host_info, local_dir, remote_dir, jar_name)
