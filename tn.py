#!/usr/bin/env python

import argparse
import TachyonNet


if __name__ == '__main__':
    AUTHOR = 'Joff Thyer'
    VERSION = '20160720_1.0'
    SPONSOR = 'Black Hills Information Security'

    print """\
[*] ======================================
[*]  TachyonNet Version %s
[*]  Author: %s (c) 2016
[*]  %s
[*] ======================================
""" % (VERSION, AUTHOR, SPONSOR)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-b', '--bindaddr', default='0.0.0.0',
        help='IP address to bind/listen on (defaults to all)'
    )
    parser.add_argument(
        '--mintcp', type=int, default=1024,
        help='lowest TCP port in range to listen on (default: 1024)'
    )
    parser.add_argument(
        '--maxtcp', type=int, default=32768,
        help='highest TCP port in range to listen on (default: 32768)'
    )
    parser.add_argument(
        '--minudp', type=int, default=1024,
        help='lowest UDP port in range to listen on (default: 1024)'
    )
    parser.add_argument(
        '--maxudp', type=int, default=32768,
        help='highest UDP port in range to listen on (default: 32768)'
    )
    parser.add_argument(
        '--bufsize', type=int, default=8192,
        help='buffer size to capture traffic (default: 8192 bytes)'
    )
    parser.add_argument(
        '-t', '--threads', type=int, default=32,
        help='number of TCP/UDP threads (default: 32)'
    )
    parser.add_argument(
        '--notcp', default=False, action='store_true',
        help='do not open TCP sockets'
    )
    parser.add_argument(
        '--noudp', default=False, action='store_true',
        help='do not open UDP sockets'
    )
    parser.add_argument(
        '-f', '--fin', default=False, action='store_true',
        help='Use 3-way/4-way FIN/ACK to teardown connections' +
            ' (defaults to TCP RESET)'
    )
    args = parser.parse_args()

    try:
        tn = TachyonNet.TachyonNet(
            mintcp=args.mintcp,
            maxtcp=args.maxtcp,
            minudp=args.minudp,
            maxudp=args.maxudp,
            bind_addr=args.bindaddr,
            tcp_reset=args.fin,
            bufsize=args.bufsize,
            udp_threads=args.threads,
            tcp_threads=args.threads,
            notcp=args.notcp,
            noudp=args.noudp
        )
        tn.run()
    except KeyboardInterrupt:
        print '\r[-] Keyboard Interrupt.  Exiting...'
        tn.stop()
    except Exception as e:
        print e
