#!/usr/bin/env python
# dispatcher.py
# URL Dispatch engine
# Author: Samuel Sekiwere <sekiskylink@gmail.com>
#
"""URL Egine

"""
import os
import sys
import eventlet
import psycopg2
import psycopg2.extras
import base64
import Queue
import time
import threading
import logging

try:
    import httplib2
    Http = httplib2.Http
except ImportError:
    import urllib2
    class Http(): # wrapper to use when httplib2 not available
        def request(self, url, method, body, headers):
            f = urllib2.urlopen(urllib2.Request(url, body, headers))
            return f.info(), f.read()

#from eventlet import db_pool
import eventlet.db_pool
from eventlet.green import socket
import socket
from eventlet.green import urllib2
from datetime import date
from threading import Thread, Event

logging.basicConfig(level=logging.DEBUG,
        format='%(asctime)s [%(process)d] %(levelname)-4s:  %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        filename='/var/log/dispatcher/dispatcher.log',
        filemode='a')
# First Things First
# Lets save pid in pidfile
PIDFILE = "/var/tmp/dispatcher.pid"
PID = str(os.getpid())
print "Current PID is:%s"%PID
if os.path.isfile(PIDFILE):
    print "%s already exists, exiting" % PIDFILE
    pidx = file(PIDFILE,'r').read().strip()
    if len(pidx) > 0:
        is_runing = os.popen("ps up %s | grep -v '^USER'|awk '{print $2}'"%pidx).read().strip()
        print is_runing
        if len(is_runing) > 0:
            print "Dispatch engine is already running..."
            sys.exit(1)
        else:
            file(PIDFILE, 'w').write(PID)
else:
    print "Dispatcher started with PID:%s"%PID
    file(PIDFILE, 'w').write(PID)

# Default Configurations
defaults = {
        'dbname':'mtrack3',
        'dbhost':'localhost',
        'dbuser':'postgres',
        'dbpass':'postgres',
        'dhis2_user':'dhis',
        'dhis2_passwd': 'L2T3cuGVj',
        'dhis2-smsinput-url':'http://mujhu.dhis2.org/sms/smsinput.action',
        'sms-sender': 'tester',
        'send-sms-url':'http://localhost:13013/cgi-bin/sendsms?username=tester&password=foobar&smsc=fake',
        'queue_process_interval':5,
        'max_num_threads': 5,
        'lang': 'en',
        'cc':'256',
        }

lang_strings = {}

# Helpers
def default(*args):
    p = [i for i in args if i or i==0]
    if p.__len__(): return p[0]
    if args.__len__(): return args[args.__len__()-1]
    return None


def myReadConf(fname):
    """Reads a config file consisting of name: value lines"""
    cfgx = {}
    splitchar = ':'
    for l in file(fname):
        l = l.strip()
        if not l: continue
        if l[0] == '#' or l.find(splitchar) < 0:
            continue # a comment
        k,v = l.strip().split(splitchar,1)
        if not k or not v:
            continue # skip over bad ones
        cfgx[k.lower().strip()] = v.strip()
    return cfgx


#Read configuration
try:
    cfg  = myReadConf('/etc/dispatcher/dispatcher.conf')

    #Make sure cfg has required configurations
    for ky, val in defaults.items():
        if not cfg.has_key(ky):
            cfg[ky] = val
except IOError, e:
    print e
    logging.error(e)
    # Instead use default configurations
    cfg = defaults

from urllib import urlencode,urlopen
def sendsms(frm, to, msg):
    params = {'from':frm,'to':to,'text':msg}
    surl = cfg['send-sms-url']
    if surl.find('?'):
        c = '&'
    else: c = '?'
    url = surl + c + urlencode(params)
    s = urlopen(url)
    return s.readlines()

def querystring_to_dict(qstr):
    try:
        return dict([x.split('=') for x in qstr.split('&')])
    except:
        return {}

def lit(**keywords):
    return keywords

def missing_param(param_list,params):
    s = ""
    for i in param_list:
        if not params.has_key(i):
            s += "%s, "%i
    return s

def read_url(url):
    HTTP_METHOD = "GET"
    auth = base64.b64encode("%(dhis2_user)s:%(dhis2_passwd)s" % cfg)
    headers = {
            'Content-type': 'application/json; charset="UTF-8"',
            'Authorization': 'Basic ' + auth
            }
    response, content = http.request(url, HTTP_METHOD, headers=headers)
    return content

def send_data(requestXml):
    HTTP_METHOD = "POST"
    url = "%sdataValueSets" % (cfg['dhis2_url'])
    print url
    auth = base64.b64encode("%(dhis2_user)s:%(dhis2_passwd)s" % cfg)
    headers = {
            'Content-type': 'text/xml; charset="UTF-8"',
            'Authorization': 'Basic ' + auth
            }
    response, content = http.request(url, HTTP_METHOD, body=requestXml, headers=headers)
    return response

pool = eventlet.GreenPool()

cp = eventlet.db_pool.ConnectionPool(psycopg2, host=cfg['dbhost'], user=cfg['dbuser'], \
        password=cfg['dbpass'], database=cfg['dbname'])

#Is connection pool valid?
try:
    xx = cp.get()
except psycopg2.OperationalError, e:
    print e
    sys.exit(1)
else:
    #put connection back to pool since
    #now we're sure the connection pool is valid
    cp.put(xx)

#cp2 = psycopg2.connect("dbname='etopup' host='localhost' user='postgres' password='postgres'")


#topup_lock = threading.Lock()
print_lock = threading.Lock()
def sync_print(text):
    with print_lock:
        print text

# If there are any database cofigurations
# they will overide those in conf file
class url_dispatcher_config:
    topup_id = 0
    transfer_id = 0

    def __init__(self,cur):
        global cfg, lang_strings
        cur.execute("SELECT * FROM misc")
        res = cur.fetchall()
        for r in res:
            if r['item'] == 'max_num_threads':
                cfg['max_num_threads'] = r['val']
            elif r['item'] == 'send-sms-url':
                cfg['send-sms-url'] = r['val']
            elif r['item'] == 'sms-sender':
                cfg['sms-sender'] = r['val']


xcon = cp.get()
dispatcher_conf = url_dispatcher_config(xcon.cursor(cursor_factory=psycopg2.extras.DictCursor))
cp.put(xcon)

http = Http()

import pprint
pp = pprint.PrettyPrinter(indent=4)
pp.pprint(cfg)

def _rts(name=None,deftext=""):
    global lang_strings
    if lang_strings.has_key(name):
        return default(lang_strings[name],deftext)
    return deftext

# End Helpers
def do_unknown(req):
    strx ="""Unknown request::: %s"""%req
    #return "Unknown request:- %s===%s\n"%(req,dispatcher_conf.max_num_threads)
    return strx

def testing(req):
    print "handling this request->",req
    return ""

def dhis2_smsinput(args=[None,0,'','']):
    conn = args[0]
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    xid = args[1]
    query_string = args[2]
    msisdn = args[3]

    if query_string:
        d = querystring_to_dict(query_string)
    else:
        cur.execute("""UPDATE request_queue SET status = 'failed', \
                ldate = current_timestamp WHERE id = %s"""%xid)
        conn.commit()
        print "Wolokoso"
        logging.error("Request [%s] body for /dhis2_smsinput is empty"%xid)
        return None

    smsinput_url = cfg['dhis2-smsinput-url']

    if d.has_key('sender') and d.has_key('message'):
        if smsinput_url.find('?') < 0:
            c = '?'
        else:
            c = ''
        url = smsinput_url + c + urlencode(d)
        # now time to call the silly dhis2 URL
        print url
        print read_url(url)
        cur.execute("UPDATE request_queue SET status = 'completed', "
                "ldate = current_timestamp, statuscode = '%s' WHERE id = %s"%('0200',xid))
        conn.commit()
        logging.debug("%s URL successfully called [id: %s]"%('/dhis2_smsinput',xid))
    return "URL dispatched"

def queue_request(arg):
    """Queue up incoming request in the database"""
    req = arg[0]
    qstr = arg[1]
    msisdn = arg[2]
    if qstr:
        conn = cp.get()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        sql = """INSERT INTO request_queue (msisdn,req_path,req_body) \
                VALUES('%s','%s','%s') RETURNING id"""%(msisdn,req,qstr)
        cur.execute(sql)
        res = cur.fetchone()
        conn.commit()
        cp.put(conn)
        logging.debug("Queued %s Request from %s with id %s"%(req,msisdn,res['id']))
        return "%s %s"%(_rts('E_REQUEST_QUEUED', \
                'Request queued with ID'),res['id'])
    else:
        logging.error("%s Request from %s with no cgi variables"%(req,msisdn))
        return "Notice: No Parameters passed"

#our handler for each request
handler = {
        "/dhis2_smsinput":queue_request,
        "/testing": queue_request
        }

queueHandler = {
        "/dhis2_smsinput":dhis2_smsinput,
        "/testing": testing
        }

#This guy handles incoming requests
def app(environ, start_response):
    if environ['REQUEST_METHOD'] != 'GET':
        start_response('403 Forbidden',[('Content-type','text/plain')])
        strx ="""Unsupported Method %s"""% \
                (environ['REQUEST_METHOD'])
        return '\n'.join([strx])
    #print environ

    pile = eventlet.GreenPile(pool)
    if environ.has_key('QUERY_STRING'):
        qstr = urllib2.unquote(environ['QUERY_STRING'])
    else: qstr = ""
    #print environ
    if environ.has_key('HTTP_X_SAT_MSISDN'):
        msisdn = urllib2.unquote(environ['HTTP_X_SAT_MSISDN'])
    else:
        #perhaps from the web interface
        #from the web interface we shall use sender for msisdn
        if qstr:
            qdict = querystring_to_dict(qstr)
            if qdict.has_key('sender'):
                msisdn = qdict['sender']
            else: msisdn = ""
        else: msisdn = ""

    reqp = environ['PATH_INFO']
    #qstr = request body
    #pile.spawn(handler.get(environ['PATH_INFO'],do_unknown),qstr)
    if handler.has_key(reqp):
        pile.spawn(handler.get(reqp),[reqp,qstr,msisdn])
    else:
        #pile.spawn(do_unknown,reqp)
        start_response('404 Not Found',[('Content-type','text/plain')])
        strx ="""Unknown request: %s"""%reqp
        return '\n'.join([strx])

    res = '\n'.join(pile)
    start_response('200 OK',[('Content-type','text/plain')])
    return [res]

req_list = Queue.Queue(10)
req_threads = []
qstop = 0

class RequestRun(Thread):
    """Consumer Thread Class"""
    def __init__(self,args=[]):
        Thread.__init__(self)
        self.args = args
    def run(self):
        conn = self.args[0]
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        global req_list

        while 1:
            try:
                qid = req_list.get()
                #print "gwe--- id===>",id
                cur.execute("SELECT msisdn,req_path, req_body, sesid FROM request_queue WHERE id = %s FOR UPDATE"%qid)
                r = cur.fetchone()
                msisdn = r['msisdn']
                path = r['req_path']
                body = r['req_body']
                sesid = r['sesid']
                #print body
                if not queueHandler.has_key(path):
                    cur.execute("UPDATE request_queue SET status='%s', \
                            ldate = current_timestamp WHERE id = %s"%('failed',qid))
                    conn.commit()
                    continue
                if not body:
                    cur.execute("UPDATE request_queue SET status='%s', \
                            ldate = current_timestamp WHERE id = %s"%('failed',qid))
                    conn.commit()
                    continue

                queueHandler.get(path)([conn,qid,body,msisdn])
                time.sleep(0.5)
                #if req_list.qsize > 0:
                #    self.workers_lounge.back_to_work()

            except Queue.Empty:
                #sync_print("%s is resting"%self.name)
                #if (self.workers_lounge.rest() == False):
                #    sync_print("%s finished working"%self.name)
                break

class RequestProcessor(Thread):
    """Request Processor Class"""
    def __init__(self):
        Thread.__init__(self)

    def run(self):
        global req_list, req_threads, qstop
        #thread_name = threading.currentThread().name
        i = 0
        while i < int(cfg['max_num_threads']):
            try:
                con =  psycopg2.connect("dbname='%s' host='%s' user='%s' password='%s'"% \
                        (cfg['dbname'],cfg['dbhost'],cfg['dbuser'],cfg['dbpass']))
            except:
                con = None
            if con:
                t = RequestRun(args=[con])
                req_threads.append(t)
            i +=1

        for t in req_threads:
            #t.setDaemon(1)
            t.start()

        if len(req_threads) == 0:
            #print "qstop became one"
            qstop = 1
        try:
            myconn = psycopg2.connect("dbname='%s' host='%s' user='%s' password='%s'"% \
                    (cfg['dbname'],cfg['dbhost'],cfg['dbuser'],cfg['dbpass']))
        except psycopg2.OperationalError:
            myconn = None

        if myconn:
            while (1 and qstop == 0):
                cur = myconn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("SELECT id FROM request_queue WHERE status='ready' ORDER BY id ASC LIMIT 1000")
                res = cur.fetchall()
                if res:
                    for r in res:
                        req_list.put(r["id"])
                time.sleep(float(cfg['queue_process_interval']))

        for t in req_threads:
            t.join()


if __name__ == '__main__':
    logging.info("Starting Processor threads....")
    b = RequestProcessor()
    b.start()
    if qstop == 1:
        req_list.join()
        b.join()
        #cp2.close()

    from eventlet import wsgi

    f = open('/var/log/dispatcher/dispatcher.log','a')
    logging.info("Starting WSGI Server....")

    wsgi.server(eventlet.listen(('',9090)),app, log=f, log_format='%(client_ip)s - -[, %(date_time)s], \
            "%(request_line)s" %(status_code)s %(body_length)s %(wall_seconds).6f')
