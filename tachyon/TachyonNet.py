#!/usr/bin/env python

import resource
import select
import socket
import struct
import time
import threading
import syslog
import os
import re
import sys
import Queue
from datetime import datetime


class TachyonNet:

    ALLSOCKETS = []
    fd2sock = {}
    done = False
    LOGQ = Queue.Queue()

    def __init__(self, bind_addr='0.0.0.0',
                 mintcp=1024, maxtcp=32768,
                 minudp=1024, maxudp=32768,
                 timeout=500, tcp_reset=False,
                 bufsize=8192, backlog=32,
                 tcp_threads=32, udp_threads=32,
                 notcp=False, noudp=False,
                 sleeptime=4,
                 logdir='%s/.tachyon_net' % (os.path.expanduser('~'))):

        self.bind_addr = bind_addr

        self.mintcp = mintcp
        self.maxtcp = maxtcp
        self.minudp = minudp
        self.maxudp = maxudp

        self.timeout = timeout
        self.tcp_reset = tcp_reset
        self.bufsize = bufsize
        self.backlog = backlog
        self.tcp_threads = tcp_threads
        self.udp_threads = udp_threads
        self.sleeptime = sleeptime
        self.notcp = notcp
        self.noudp = noudp
        self.logdir = logdir
        self.logfile = '%s/tn.log' % (self.logdir)

        # initialize some variables
        self.lock = threading.Lock()
        self.tcp_good = 0
        self.tcp_bad = 0
        self.udp_good = 0
        self.udp_bad = 0
        self.tcp_connects = 0
        self.udp_connects = 0
        self.tcp_bytes = 0
        self.udp_bytes = 0
        return

    def run(self):

        print '[+] --< Initializing >--'
        udp_ports = self.maxudp - self.minudp
        tcp_ports = self.maxtcp - self.mintcp
        r_ports = udp_ports + tcp_ports

        r_nofile = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        r_nofile_req = r_ports * 1.5
        if udp_ports < 0 or tcp_ports < 0:
            raise Exception(
                '[-] Are you smoking something good?\n' +
                '[-] Have you temporarily lost your nut?\n' +
                '[-] You want to listen on a negative no. of ports?\n' +
                '[-] maxport must be greater than the minport!!!'
            )
        elif r_nofile < r_nofile_req:
            raise Exception(
                '[-] ERROR: INSUFFICIENT AVAILABLE FILE DESCRIPTORS.\n' +
                '[-] Trying to listen on %d TCP/UDP ports.\n' % (r_ports) +
                '[-] %d file descriptors are available.\n' % (r_nofile) +
                '[-] %d file descriptors are required.\n' % (r_nofile_req) +
                '[-] Modify /etc/security/limits.conf (Debian) ' +
                'OR reduce the port count.'
            )
        elif self.notcp and self.noudp:
            raise Exception('[-] Seriously?')

        # open syslog
        syslog.openlog(
            logoption=syslog.LOG_PID,
            facility=syslog.LOG_USER
        )

        # check logdir
        if not os.path.exists(self.logdir):
            os.mkdir(self.logdir)

        # start logger thread
        t = threading.Thread(target=self.logger)
        t.name = '_logger'
        t.daemon = True
        t.start()
        print '[+] Logging to syslog, and directory: [%s]' % (self.logdir)

        if not self.notcp:
            print '[+] Opening %d TCP sockets from port %d to %d' % \
                  (tcp_ports, self.mintcp, self.maxtcp - 1)
            self.start_tcp_threads()
            time.sleep(self.sleeptime)
            print '[+] %d TCP sockets opened, %d failed.' % \
                  (self.tcp_good, self.tcp_bad)

        if not self.noudp:
            print '[+] Opening %d UDP sockets from port %d to %d' % \
                  (udp_ports, self.minudp, self.maxudp - 1)
            self.start_udp_threads()
            time.sleep(self.sleeptime)
            print '[+] %d UDP sockets opened, %d failed.' % \
                  (self.udp_good, self.udp_bad)

        # loops and waits
        i = 0
        spinner = '/-\|'
        while not self.done:
            print '\r[+] --< \x1b[1mListening \x1b[30m' + \
                  ' [ tcp:\x1b[32m%4d/%-6d\x1b[30m |' % \
                  (self.tcp_connects, self.tcp_bytes) + \
                  ' udp:\x1b[31m%4d/%-6d\x1b[30m ]' % \
                  (self.udp_connects, self.udp_bytes) + \
                  ' (%s)\x1b[0m >--%s' % (
                      spinner[i % len(spinner)], 6 * '\x08'
                  ),
            sys.stdout.flush()
            time.sleep(self.sleeptime / 4)
            i += 1
        return

    def stop(self):
        self.done = True
        print '\r[+] Terminating socket threads...'
        for t in threading.enumerate():
            if re.match(r'_(tdp|udp)\d{1,}', t.name):
                t.join()
        return

    def logger(self):
        lf = open(self.logfile, 'a')
        while True:
            d = self.LOGQ.get()
            if d[0] == 'msg':
                syslog.syslog(d[1])
                now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                lf.write('%s: %s\n' % (now, d[1]))
                lf.flush()
            elif d[0] == 'data':
                self.logger_writedata(d[1])
            self.LOGQ.task_done()

    def logger_writedata(self, msg):
        proto = msg[0]
        src = msg[1]
        dst = msg[2]
        data = msg[3]
        directory = '%s/%s' % (
            self.logdir,
            datetime.utcnow().strftime('%Y%m%d')
        )
        if not os.path.exists(directory):
            os.mkdir(directory)
        filename = '%s/%s_%s_%s__%s_%s.log' % (
            directory, proto.lower(),
            src[0], src[1], dst[0], dst[1]
        )
        f = open(filename, 'w')
        f.write(data)
        f.close()
        return

    def do_msglog(self, msg):
        self.LOGQ.put(('msg', msg))

    def do_datalog(self, proto, src, dst, data):
        self.LOGQ.put(('data', (proto, src, dst, data)))

    def start_tcp_threads(self):
        tcp_ports2thread = [[] for x in range(self.tcp_threads)]
        for i in range(self.mintcp, self.maxtcp):
            tcp_ports2thread[i % self.tcp_threads].append(i)

        for i in range(self.tcp_threads):
            t = threading.Thread(
                target=self.tcp_thread_main,
                args=[tcp_ports2thread[i % self.tcp_threads]]
            )
            t.name = '_tcp%02d' % (i)
            t.start()
        print '[+] %d TCP listener threads active.' % (self.tcp_threads)
        return

    def start_udp_threads(self):
        udp_ports2thread = [[] for x in range(self.udp_threads)]
        for i in range(self.minudp, self.maxudp):
            udp_ports2thread[i % self.udp_threads].append(i)

        for i in range(self.udp_threads):
            t = threading.Thread(
                target=self.udp_thread_main,
                args=[udp_ports2thread[i % self.udp_threads]]
            )
            t.name = '_udp%02d' % (i)
            t.start()
        print '[+] %d UDP listener threads active.' % (self.udp_threads)
        return

    def tcp_thread_main(self, portlist):
        mux = self.bind_tcp_sockets(portlist)
        self.tcp_connections(mux)
        return

    def udp_thread_main(self, portlist):
        mux = self.bind_udp_sockets(portlist)
        self.udp_connections(mux)
        return

    def bind_tcp_sockets(self, portlist):
        mux = select.poll()
        for port in portlist:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind((self.bind_addr, port))
                s.listen(self.backlog)
                s.setblocking(0)
                if self.tcp_reset:
                    s.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_LINGER,
                        struct.pack('ii', 1, 0)
                    )
                mux.register(s)
                self.fd2sock[s.fileno()] = {'fileno': s, 'proto': 6}
                self.ALLSOCKETS.append(s)

                self.lock.acquire()
                self.tcp_good += 1
                self.lock.release()

            except socket.error as e:
                self.do_msglog('TCP: error binding port %d: %s' % (port, e))
                self.lock.acquire()
                self.tcp_bad += 1
                self.lock.release()
                continue
        return mux

    def bind_udp_sockets(self, portlist):
        mux = select.poll()
        for port in portlist:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.bind((self.bind_addr, port))
                mux.register(s)
                self.fd2sock[s.fileno()] = {'fileno': s, 'proto': 17}
                self.ALLSOCKETS.append(s)
                self.lock.acquire()
                self.udp_good += 1
                self.lock.release()
            except socket.error as e:
                self.do_msglog(
                    'UDP: error binding port %d: %s' % (port, e)
                )
                self.lock.acquire()
                self.udp_bad += 1
                self.lock.release()
                continue
        return mux

    def tcp_connections(self, mux):
        while not self.done:
            ready = mux.poll(self.timeout)
            for fd, event in ready:
                if event & select.POLLIN:
                    self.read_data(fd)
        return

    def udp_connections(self, mux):
        while not self.done:
            ready = mux.poll()
            for fd, event in ready:
                if event & select.POLLIN:
                    self.read_data(fd)
            time.sleep(self.timeout / 1000.0)
        return

    def read_data(self, fd):
        s = self.fd2sock[fd]['fileno']
        proto = self.fd2sock[fd]['proto']
        server_addr = s.getsockname()
        try:
            if proto == 6:
                sproto = 'TCP'
                cs, client_addr = s.accept()
                data = cs.recv(self.bufsize)
                cs.close()
                self.lock.acquire()
                self.tcp_connects += 1
                self.tcp_bytes += len(data)
                self.lock.release()
            elif proto == 17:
                sproto = 'UDP'
                data, client_addr = s.recvfrom(self.bufsize)
                self.lock.acquire()
                self.udp_connects += 1
                self.udp_bytes += len(data)
                self.lock.release()

            self.do_msglog(
                '%s: %s:%d -> %s:%d: %d bytes read.' %
                (
                    sproto,
                    client_addr[0], client_addr[1],
                    server_addr[0], server_addr[1],
                    len(data)
                )
            )
            self.do_datalog(sproto, client_addr, server_addr, data)

        except Exception as e:
            self.do_msglog('ERROR: %s' % (e))
            pass
        return

    def __del__(self):
        for s in self.ALLSOCKETS:
            s.close()

if __name__ == '__main__':
    print 'This is the module.  You need to import and use this.'