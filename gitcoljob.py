#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import os
import json
import sys
import time
import hashlib
import urllib
import argparse
import plistlib
import urlparse
import os, git
from git import Repo
import subprocess
import re
import datetime
import requests
import hmac
import base64

reload(sys)
sys.setdefaultencoding('utf-8')
parser = argparse.ArgumentParser()
parser.add_argument('-start', '--start', help='collect start',  type=str)
parser.add_argument('-end', '--end', help='collect end',  type=str)
args = parser.parse_args()

# 提交list
authorCommitBranchList = []
#webhook机器人请求地址
webhook_url = "xxx"
webhook_secret = "xxx"
#消息头部
headers = {'Content-Type': 'application/json'}
#代码统计需要更新数据库的API
url_update = "xxx"
#包装头部
firefox_headers = {'User-Agent'  : 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) Gecko/20100101 Firefox/23.0',
                   'Content-Type': 'application/json',
                   }
collectdayDate = None
kdir_list=[] #存放工程目录列表数组
kauthorEmail_list=[] #存放作者邮箱列表数组
kgitlineDict = dict() #存放行数map，key为email，value为代码行数
illegalAuthorList = [] #存放非法的作者列表数组

# 处理shell脚本读取log为可访问对象
def dealshellCommandLog(shellCommand):
    proc = subprocess.Popen(shellCommand,shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    out, err = proc.communicate()
    print "out: ", out.splitlines()
    print "error: ", err
    return out.splitlines()

def stripStringListUtil(list):
    tmpList = []
    for stringObj in list:
        tmpString = stringObj.strip('*')
        tmpList.append(tmpString.strip())
    return tmpList


def log(logcontent):
    dt = datetime.datetime.now()
    formatDate = dt.strftime('%Y-%m-%d %H:%M:%S.%f')
    logcontent = '%s:%s' % (formatDate, logcontent)
    print(logcontent)
    sys.stdout.flush()

def handleCurrentProject(dirPath):
    remote_branches = dealshellCommandLog("git branch -r")
    remote_branches = stripStringListUtil(remote_branches)
    if (len(remote_branches) > 1):
        # 删除origin/HEAD -> origin/master
        del (remote_branches[0])
    remotejson_str = json.dumps(remote_branches)
    log('remote= ' + remotejson_str)
    localBranchs = dealshellCommandLog("git branch")
    localBranchs = stripStringListUtil(localBranchs)
    localjson_str = json.dumps(localBranchs)
    log('local= ' + localjson_str)
    for rebranch in remote_branches:
        shortrebranch = rebranch.replace('origin/','')
        if shortrebranch in localBranchs:
            try:
                os.system('git checkout .')
                os.system('git checkout ' + shortrebranch)
                os.system('git pull --rebase')
            except Exception, error:
                print error
        else:
            os.system('git checkout -b ' + shortrebranch + ' ' + rebranch)

# 统计当前分支的git提交数量
def handleCurrentBranchGitCount(dirPath,shortrebranch):
    tmpauthorlist = dealshellCommandLog("git log --format='%ae' | sort -u")
    for author in tmpauthorlist:
        if author not in kauthorEmail_list:
            kauthorEmail_list.append(author)
        else:
            log("kauthorEmail_list has contaied: " + author)
    for email in tmpauthorlist:
        time.sleep(0.2)
        if "@" in email and (".com" in email or ".cn" in email):
            oneDayShell = "git log --after=" + '"' + collectdayDate + '"' + " --before=" + '"' + untildayDate + '"' + " --author=" + '"' + email + '"' + " --no-merges | wc -l"
            count_list = dealshellCommandLog(oneDayShell)
            count_list = stripStringListUtil(count_list)
            if len(count_list) > 0:
                count = int(count_list[0])
                if count > 0 :
                    authorCommitBranchList.append(email + '&' + dirPath + '&' + shortrebranch)
                oldCt = kgitlineDict.get(email)
                if oldCt is None:
                    oldCt = 0
                newCt = count + oldCt
                kgitlineDict[email] = newCt
            json_str = json.dumps(count_list)
        else:
            if email not in illegalAuthorList:
                illegalAuthorList.append(email)

def updateGitDB(param):
    day_time = long(time.mktime(datetime.date.today().timetuple())) - 86400
    log("昨日凌晨0点时间戳:" + str(day_time))
    requestTimes = []
    requestEmails = []
    requestLines = []
    requestDict = dict()
    for key,value in param.items():
        requestEmails.append(key)
        requestLines.append(value)
        requestTimes.append(day_time)
    requestDict['emails'] = requestEmails
    requestDict['lines'] = requestLines
    requestDict['times'] = requestTimes
    log("请求入库数据requestDict :" + json.dumps(requestDict))
    response = requests.post(
        url_update,
        data=json.dumps(requestDict),
        headers=firefox_headers
    )
    log("数据库更新完毕！")

def sendDingDing():
    log("钉钉消息推送开始！")
    timeArray = time.strptime(collectdayDate, "%Y-%m-%d %H:%M:%S")
    otherStyleTime = time.strftime("%Y/%m/%d", timeArray)
    content = otherStyleTime +"当天提交结果:\n"
    sortGitList = sorted(kgitlineDict.items(), key=lambda x: x[1], reverse=True)
    for item in sortGitList:
        print(item)
        content = content + item[0] + ":  " + str(item[1]) + "\n"
    data = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }
    timestamp = long(round(time.time() * 1000))
    secret = webhook_secret
    secret_enc = bytes(secret).encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, secret)
    string_to_sign_enc = bytes(string_to_sign).encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.quote_plus(base64.b64encode(hmac_code))
    print(timestamp)
    print(sign)
    newwebhook_url = webhook_url + "&timestamp=" + str(timestamp) + "&sign=" + sign
    # 使用post请求推送消息
    try:
        requests.post(newwebhook_url, data=json.dumps(data), headers=headers)
    except Exception, error:
        print error
    log("钉钉消息推送结束！")
    #更新到db
    updateGitDB(kgitlineDict)



# 统计脚本开始
os.chdir('/Users/xxx/developDir')
os.system('echo "" > gitcoljob.txt')
log("git collection begin")
# 获取昨天的提交数量
if args.start is not None and len(args.start) > 6:
    collectdayDate = args.start
else:
    collectdayDate = (datetime.date.today() + datetime.timedelta(days=-1)).strftime("%Y-%m-%d %H:%M:%S")
timeArray = time.strptime(collectdayDate, "%Y-%m-%d %H:%M:%S")
collectTimeStamp = int(time.mktime(timeArray))
if args.end is not None and len(args.end) > 6:
    untildayDate = args.end
else:
    untildayDate = datetime.date.today().strftime('%Y-%m-%d %H:%M:%S')
sys.stdout.flush()
cur_pwd = os.getcwd()
path = cur_pwd
objects=os.listdir(path)
for obj in objects:
    if os.path.isdir(os.path.join(path, obj)):
        kdir_list.append(os.path.join(path, obj))
        log("dir：" + json.dumps(obj))
    else:
        log("file：" + json.dumps(obj))
log("目录列表：" + json.dumps(kdir_list))
for dirPath in kdir_list:
    os.chdir(dirPath)
    os.system('git checkout .')
    os.system('git pull --rebase')
    handleCurrentProject(dirPath)
for dirPath in kdir_list:
    os.chdir(dirPath)
    changeTimeBranchs = dealshellCommandLog("git for-each-ref --sort=committerdate refs/heads/ --format='%(committerdate:short) %(refname:short)'")
    for change in changeTimeBranchs:
        list = change.split();
        if (len(list) == 2):
            comittime = list[0]
            shortrebranch = list[1]
            comittime = comittime + " 00:00:00"
            comittimeArray = time.strptime(comittime, "%Y-%m-%d %H:%M:%S")
            comittimeStamp = int(time.mktime(comittimeArray))
            if comittimeStamp >= collectTimeStamp:
                os.system('git checkout .')
                os.system('git checkout ' + shortrebranch)
                handleCurrentBranchGitCount(dirPath, shortrebranch)
            else:
                log("该分支昨日无更新：" + shortrebranch)
sendDingDing()
log("git collection finish")

