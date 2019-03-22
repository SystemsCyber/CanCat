import Queue
import cancat
import struct
from J1939db import *
from cancat import *

import vstruct
from vstruct.bitfield import *

PF_RQST =       0xea
PF_TP_DT =      0xeb
PF_TP_CM =      0xec
PF_ADDRCLAIM =  0xee
PF_PROPRIETRY=  0xef
PF_KWP1 =       0xdb
PF_KWP2 =       0xda
PF_KWP3 =       0xce
PF_KWP4 =       0xcd

CM_RTS   =       0x10
CM_CTS   =       0x11
CM_EOM   =       0x13
CM_ABORT =       0xff
CM_BAM   =       0x20

class NAME(VBitField):
    def __init__(self):
        VBitField.__init__(self)
        self.arbaddrcap = v_bits(1)
        self.ind_group = v_bits(3)
        self.vehicle_system_instance = v_bits(4)
        self.vehicle_system = v_bits(7)
        self.reserved = v_bits(1)
        self.function = v_bits(8)
        self.function_instance = v_bits(5)
        self.ecu_instance = v_bits(3)
        self.mfg_code = v_bits(11)
        self.identity_number = v_bits(21)

    def minrepr(self):
        mfgname = mfg_lookup.get(self.mfg_code)
        return "id: 0x%x mfg: %s" % (self.identity_number, mfgname)

def parseName(name):
    namebits= NAME()
    rname = name[::-1]
    namebits.vsParse(rname)
    return namebits

def reprExtMsgs(msgs):
    try:
        out = ['Ext Msg: %.2x->%.2x (%.2x%.2x%.2x) (len: 0x%x)' % (msgs['sa'], msgs['da'], msgs['pgn2'], msgs['pgn1'], msgs['pgn0'], msgs['totsize'])]
        for arbtup, msg in msgs.get('msgs'):
            out.append(msg[1:].encode('hex'))

        data = ''.join(out[1:]).decode('hex')
        strings = getAscii(data)

        if len(strings):
            return ' '.join(out) + "  %r" % (strings)
        return ' '.join(out)
    except Exception, e:
        return ' Exception: %r (%r)' % (e, msgs)

def meldExtMsgs(msgs):
    out = []
    length = msgs.get('totsize')
    for arbtup, msg in msgs.get('msgs'):
        out.append(msg[1:])

    outval = ''.join(out)
    if outval[length:] == '\xff'*(len(outval)-length):
        #print "truncating %r to size %r" % (outval, length)
        outval = outval[:length]
    #else:
        #print "NOT truncating %r to size %r" % (outval, length)

    return outval

### renderers for specific PF numbers
def pf_c9(idx, ts, arbtup, data, j1939):
    ''' repr handler for c9 '''
    b4 = data[3]
    req = "%.2x %.2x %.2x" % ([ord(d) for d in data[:3]])
    usexferpfn = ('', 'Use_Transfer_PGN', 'undef', 'NA')[b4 & 3]
    
    return "Request2: %s %s" % (req,  usexferpgn)

def pf_ea(idx, ts, (prio, edp, dp, pf, ps, sa), data, j1939):
    ''' repr handler for ea '''
    return "Request: %s" % (data[:3].encode('hex'))

def pf_eb(idx, ts, arbtup, data, j1939):
    ''' repr handler for eb '''
    (prio, edp, dp, pf, da, sa) = arbtup
    if len(data) < 1:
        return 'TP ERROR: NO DATA!'

    idx = ord(data[0])

    msgdata = 'TP.DT idx: %.x' % idx
    nextline = ''
    extmsgs = j1939.getExtMsgs(sa, da)
    extmsgs['msgs'].append((arbtup, data))

    if len(extmsgs['msgs']) >= extmsgs['length']:
        j1939.clearExtMsgs(sa, da)
        ts = extmsgs.get('ts', 0.0)
        nextline = '  %3.3f: %s' % (ts, reprExtMsgs(extmsgs))

    if j1939.skip_TPDT:
        if not len(nextline):
            return cancat.DONT_PRINT_THIS_MESSAGE 

        else:
            return (cancat.DONT_PRINT_THIS_MESSAGE, nextline)

    if len(extmsgs['msgs']) > extmsgs['length']:
            #print "ERROR: too many messages in Extended Message between %.2x -> %.2x\n\t%r" % (sa, da, extmsgs['msgs'])
            pass

    if len(nextline):
        return msgdata, nextline+'\n'

    return msgdata

def pf_ec(idx, ts, arbtup, data, j1939):
    ''' repr handler for ec '''
    def tp_cm_10(idx, ts, arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)
        
        # check for old stuff
        prefix = ''
        extmsgs = j1939.getExtMsgs(sa, da)
        if len(extmsgs['msgs']):
            extmsgs['ts'] = 0.0
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            prefix = " new TP message, without closure...: \n\t%r\n" % reprExtMsgs(extmsgs)

        j1939.clearExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['ts'] = ts
        extmsgs['idx'] = idx
        extmsgs['pgn2'] = pgn2
        extmsgs['pgn1'] = pgn1
        extmsgs['pgn0'] = pgn0
        extmsgs['maxct'] = maxct
        extmsgs['length'] = pktct
        extmsgs['totsize'] = totsize
        extmsgs['type'] = TP_DIRECT
        extmsgs['adminmsgs'].append((arbtup, data))

        return prefix + 'TP.CM_RTS size:%.2x pktct:%.2x maxpkt:%.2x PGN: %.2x%.2x%.2x' % \
                (totsize, pktct, maxct, pgn2, pgn1, pgn0)

    def tp_cm_11(idx, ts, arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, maxpkts, nextpkt, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BBBHBBB', data)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['adminmsgs'].append((arbtup, data))

        return 'TP.CM_CTS        maxpkt:%.2x nxtpkt:%.2x PGN: %.2x%.2x%.2x' % \
                (maxpkts, nextpkt, pgn2, pgn1, pgn0)

    def tp_cm_13(idx, ts, arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # not sure what to do with this now that we've cleared buffers by this point...
        # for now, just drop it.
        #extmsgs = j1939.getExtMsgs(sa, da)
        #extmsgs['adminmsgs'].append((arbtup, data))

        return 'TP.EndOfMsgACK PGN: %.2x%.2x%.2x\n\t%r' % \
                (pgn2, pgn1, pgn0, msgdata)

    def tp_cm_20(idx, ts, arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # check for old stuff
        prefix=''
        extmsgs = j1939.getExtMsgs(sa, da)
        if len(extmsgs['msgs']):
            extmsgs['ts'] = 0.0
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            prefix = " new TP message, without closure...: \n\t%r\n" % reprExtMsgs(extmsgs)

        j1939.clearExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['ts'] = ts
        extmsgs['idx'] = idx
        extmsgs['pgn2'] = pgn2
        extmsgs['pgn1'] = pgn1
        extmsgs['pgn0'] = pgn0
        extmsgs['maxct'] = reserved
        extmsgs['length'] = pktct
        extmsgs['totsize'] = totsize
        extmsgs['type'] = TP_BAM
        extmsgs['adminmsgs'].append((arbtup, data))

        return prefix + 'TP.CM_BAM-Broadcast size:%.2x pktct:%.2x PGN: %.2x%.2x%.2x' % \
                (totsize, pktct, pgn2, pgn1, pgn0)

    tp_cm_handlers = {
            CM_RTS:     ('RTS',           tp_cm_10),
            CM_CTS:     ('CTS',           tp_cm_11),
            CM_EOM:     ('EndOfMsgACK',   None),
            CM_BAM:     ('BAM-Broadcast', tp_cm_20),
            CM_ABORT:   ('Abort',         None),
            }

    cb = ord(data[0])

    htup = tp_cm_handlers.get(cb)
    if htup != None:
        subname, cb_handler = htup

        if cb_handler == None:
            if j1939.skip_TPDT:
                return cancat.DONT_PRINT_THIS_MESSAGE 

            return 'TP.CM_%s' % subname

        newmsg = cb_handler(idx, ts, arbtup, data, j1939)

        if j1939.skip_TPDT:
            return cancat.DONT_PRINT_THIS_MESSAGE 

        if newmsg == None:
            return 'TP.CM_%s' % subname

        return newmsg

    return 'TP.CM_%.2x' % cb

def pf_ee(idx, ts, (prio, edp, dp, pf, ps, sa), data, j1939):
    ''' repr handler for ee '''
    if ps == 255 and sa == 254:
        return 'CANNOT CLAIM ADDRESS'
    
    addrinfo = parseName(data).minrepr()
    return "Address Claim: %s" % addrinfo

def pf_ef(idx, ts, (prio, edp, dp, pf, ps, sa), data, j1939):
    ''' repr handler for ef '''
    if dp:
        return 'Proprietary A2'

    return 'Proprietary A1'
    
def pf_ff(idx, ts, (prio, edp, dp, pf, ps, sa), data, j1939):
    ''' repr handler for ff '''
    pgn = "%.2x :: %.2x:%.2x - %s" % (sa, pf,ps, data.encode('hex'))
    return "Proprietary B %s" % pgn

# for repr only
pgn_pfs = {
        0x93:   ("Name Management", None),
        0xc9:   ("Request2",        pf_c9),
        0xca:   ('Transfer',        None),
        0xe8:   ("ACK        ",     None),
        0xea:   ("Request      ",   pf_ea),
        0xeb:   ("TP.DT",           pf_eb),
        0xec:   ("TP.CM",           pf_ec),
        0xee:   ("Address Claim",   pf_ee),
        0xef:   ("Proprietary",     pf_ef),
        #0xfe:   ("Command Address", None),
        0xff:   ("Proprietary B",   pf_ff),
        }

def parseArbid(arbid):
    (prioPlus,
        pf,
        ps,
        sa) = struct.unpack('BBBB', struct.pack(">I", arbid))

    prio = prioPlus >> 2
    edp = (prioPlus >> 1) & 1
    dp = prioPlus & 1

    return prio, edp, dp, pf, ps, sa

def emitArbid(prio, edp, dp, pf, ps, sa):
    prioPlus = prio<<2 | (edp<<1) | dp
    return struct.unpack(">I", struct.pack('BBBB', prioPlus, pf, ps, sa))[0]


############  J1939 Extended Message Stack  #############
def ec_handler(j1939, idx, ts, arbtup, data):
    def tp_cm_10(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)
        
        # check for old stuff
        extmsgs = j1939.getRealExtMsgs(sa, da)
        if extmsgs != None and len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            j1939.saveRealExtMsg(idx-1, ts, sa, da, (0,0,0), meldExtMsgs(extmsgs), TP_DIRECT_BROKEN, idx-1)

        j1939.clearRealExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getRealExtMsgs(sa, da, create=True)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['ts'] = ts
        extmsgs['idx'] = idx
        extmsgs['pgn2'] = pgn2
        extmsgs['pgn1'] = pgn1
        extmsgs['pgn0'] = pgn0
        extmsgs['maxct'] = maxct
        extmsgs['length'] = pktct
        extmsgs['totsize'] = totsize
        extmsgs['type'] = TP_DIRECT
        extmsgs['adminmsgs'].append((arbtup, data))

        # RESPOND!
        if da in j1939.myIDs:
            response = struct.pack('<BBBHBBB', CM_CTS, pktct, 1, 0, pgn2, pgn1, pgn0)
            j1939.J1939xmit(0xec, sa, da, response, prio)

    def tp_cm_11(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, maxpkts, nextpkt, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BBBHBBB', data)

        # store extended message information for other stuff...
        extmsgs = j1939.getRealExtMsgs(sa, da)
        if extmsgs != None:
            extmsgs['adminmsgs'].append((arbtup, data))

        # SOMEHOW WE TRIGGER THE CONTINUAITON OF TRANSMISSION

    def tp_cm_13(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # print out extended message and clear the buffers.
        extmsgs = j1939.getRealExtMsgs(sa, da)
        if extmsgs != None:
            extmsgs['adminmsgs'].append((arbtup, data))

        j1939.clearRealExtMsgs(sa, da)
        # Coolio, they just confirmed receipt, we're done!
        # Probably need to trigger some mechanism telling the originator

    def tp_cm_20(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # check for old stuff
        extmsgs = j1939.getRealExtMsgs(sa, da)
        if extmsgs != None and len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            j1939.saveRealExtMsg(idx-1, ts, sa, da, (0,0,0), meldExtMsgs(extmsgs), TP_DIRECT_BROKEN, idx-1)

        j1939.clearRealExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getRealExtMsgs(sa, da, create=True)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['ts'] = ts
        extmsgs['idx'] = idx
        extmsgs['pgn2'] = pgn2
        extmsgs['pgn1'] = pgn1
        extmsgs['pgn0'] = pgn0
        extmsgs['maxct'] = 0
        extmsgs['length'] = pktct
        extmsgs['totsize'] = totsize
        extmsgs['type'] = TP_BAM
        extmsgs['adminmsgs'].append((arbtup, data))

    tp_cm_handlers = {
            CM_RTS:     ('RTS',           tp_cm_10),
            CM_CTS:     ('CTS',           tp_cm_11),
            CM_EOM:     ('EndOfMsgACK',   tp_cm_13),
            CM_BAM:     ('BAM-Broadcast', tp_cm_20),
            CM_ABORT:   ('Abort',         None),
            }

    cb = ord(data[0])
    #print "ec: %.2x%.2x %.2x" % (arbtup[3], arbtup[4], cb)

    htup = tp_cm_handlers.get(cb)
    if htup != None:
        subname, cb_handler = htup

        if cb_handler != None:
            cb_handler(arbtup, data, j1939, idx, ts)

def eb_handler(j1939, idx, ts, arbtup, data):
    (prio, edp, dp, pf, da, sa) = arbtup
    if len(data) < 1:
        j1939.log('pf=0xeb: TP ERROR: NO DATA!')
        return

    extmsgs = j1939.getRealExtMsgs(sa, da)
    if extmsgs == None:
        j1939.log('eb without ec: %r' % data.encode('hex'))
        return

    extmsgs['msgs'].append((arbtup, data))
    if len(extmsgs['msgs']) >= extmsgs['length']:
        #print "eb_handler: saving: %r %r" % (len(extmsgs['msgs']) , extmsgs['length'])
        tidx = extmsgs['idx']
        pgn2 = extmsgs['pgn2']
        pgn1 = extmsgs['pgn1']
        pgn0 = extmsgs['pgn0']
        mtype = extmsgs['type']

        j1939.saveRealExtMsg(tidx, ts, sa, da, (pgn2, pgn1, pgn0), meldExtMsgs(extmsgs), mtype, idx)
        j1939.clearRealExtMsgs(sa, da)

        # if this is the end of a message to *me*, reply accordingly
        if da in j1939.myIDs:
            if extmsgs['idx'] == -1:
                j1939.log("TP_DT_handler: missed beginning of message, not sending EOM: %r" % \
                        repr(extmsgs), 1)
                return

            j1939.log("tp_stack: sending EOM  extmsgs: %r" % extmsgs, 1)
            pgn2 = extmsgs['pgn2']
            pgn1 = extmsgs['pgn1']
            pgn0 = extmsgs['pgn0']
            totsize = extmsgs['totsize']
            maxct = extmsgs['maxct']
            pktct = extmsgs['length']

            data = struct.pack('<BHBBBBB', CM_EOM, totsize, pktct, maxct, pgn2, pgn1, pgn0)
            j1939.J1939xmit(PF_TP_CM, sa, da,  data, prio=prio)

pfhandlers = {
        PF_TP_CM : ec_handler,
        PF_TP_DT : eb_handler,
        }
TP_BAM = 20
TP_DIRECT = 10
TP_DIRECT_BROKEN=9

class TimeoutException(Exception):
    pass

class J1939(cancat.CanInterface):
    def __init__(self, port=serialdev, baud=baud, verbose=False, cmdhandlers=None, comment='', load_filename=None, orig_iface=None):
        self.myIDs = []
        self._reprExtMsgs = {}
        self._RealExtMsgs = {}
        self._RealExtMsgParts = {}
        self.skip_TPDT = False
        self._last_recv_idx = -1

        self._threads = []

        CanInterface.__init__(self, port=port, baud=baud, verbose=verbose, cmdhandlers=cmdhandlers, comment=comment, load_filename=load_filename, orig_iface=orig_iface)

        # setup the message handler event offload thread
        self._mhe_queue = Queue.Queue()
        mhethread = threading.Thread(target=self._mhe_runner)
        mhethread.setDaemon(True)
        mhethread.start()
        self._threads.append(mhethread)

        self.register_handler(CMD_CAN_RECV, self._j1939_can_handler)

    def _getSessionData(self):
        savegame = CanCat._getSessionData()
        savegame['RealExtMsgs'] = self._RealExtMsgs
        savegame['RealExtMsgParts'] = self._RealExtMsgParts
        savegame['J1939_IDs'] = self.myIDs
        savegame['J1939_LastRecvIdx'] = self._last_recv_idx
        return savegame

    def _reprCanMsg(self, idx, ts, arbid, data, comment=None):
        if comment == None:
            comment = ''

        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        # give name priority to the Handler, then the manual name (this module), then J1939PGNdb
        pfmeaning, handler = pgn_pfs.get(pf, ('',None))
        nextline = ''

        if handler != None:
            enhanced = handler(idx, ts, arbtup, data, self)
            if enhanced == cancat.DONT_PRINT_THIS_MESSAGE:
                return enhanced

            if enhanced != None:
                if type(enhanced) in (list, tuple) and len(enhanced):
                    pfmeaning = enhanced[0]
                    if len(enhanced) > 1:
                        nextline = '\n'.join(list(enhanced[1:]))

                    # if we get multiple lines and the first is DONT_PRINT_THIS_MESSAGE, 
                    # then just return nextline
                    if pfmeaning == cancat.DONT_PRINT_THIS_MESSAGE:
                        return nextline

                    nextline = '\n' + nextline

                else:
                    pfmeaning = enhanced

        elif not len(pfmeaning):
            pgn = (pf<<8) | ps
            res = J1939PGNdb.get(pgn)
            if res == None:
                res = J1939PGNdb.get(pf<<8)
            if res != None:
                pfmeaning = res.get("Name")

        return "%.8d %8.3f pri/edp/dp: %d/%d/%d, PG: %.2x %.2x  Source: %.2x  Data: %-18s  %s\t\t%s%s" % \
                (idx, ts, prio, edp, dp, pf, ps, sa, data.encode('hex'), pfmeaning, comment, nextline)


    def _getLocals(self, idx, ts, arbid, data):
        prio, edp, dp, pf, ps, sa = parseArbid(arbid)
        pgn = (pf<<8) | ps
        lcls = {'idx':idx, 
                'ts':ts, 
                'arbid':arbid, 
                'data':data, 
                'priority':prio, 
                'edp':edp, 
                'dp':dp, 
                'pf':pf, 
                'ps':ps, 
                'sa':sa, 
                'pgn':pgn,
                'da':ps,
                'ge':ps,
                }

        return lcls

    def _j1939_can_handler(self, message, none):
        '''
        this function is run for *Every* received CAN message... and is executed from the 
        XMIT/RECV thread.  it *must* be fast!
        '''
        #print repr(self), repr(cmd), repr(message)
        arbid, data = self._splitCanMsg(message)
        idx, ts = self._submitMessage(CMD_CAN_RECV, message)

        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        pfhandler = pfhandlers.get(pf)
        if pfhandler != None:
            self.queueMessageHandlerEvent(pfhandler, idx, ts, arbtup, data)
            #pfhandler(self, idx, ts, arbtup, data)

        #print "submitted message: %r" % (message.encode('hex'))


    def queueMessageHandlerEvent(self, pfhandler, idx, ts, arbtup, data):
        self._mhe_queue.put((pfhandler, idx, ts, arbtup, data))

    def _mhe_runner(self):
        while self._go:
            worktup = None
            try:
                worktup = self._mhe_queue.get(1)
                if worktup == None:
                    continue

                pfhandler, idx, ts, arbtup, data = worktup
                pfhandler(self, idx, ts, arbtup, data)

            except Exception, e:
                print "MsgHandler ERROR: %r (%r)" % (e, worktup)
                if self.verbose:
                    sys.excepthook(*sys.exc_info())


        
    # functions to support the J1939TP Stack (real stuff, not just repr)
    def getRealExtMsgs(self, sa, da, create=False):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        returns a message list for a given source and destination (sa, da)

        if no list exists for this pairing, one is created and an empty list is returned
        '''
        msglists = self._RealExtMsgParts.get(sa)
        if msglists == None:
            msglists = {}
            self._RealExtMsgParts[sa] = msglists

        mlist = msglists.get(da)
        if mlist == None:
            if create:

                mlist = {
                        'ts':0.0,
                        'idx': -1,
                        'pgn2':None,   
                        'pgn1':None, 
                        'pgn0':None, 
                        'maxct':0xff,
                        'length':0, 
                        'totsize':0,
                        'type':None, 
                        'msgs':[], 
                        'adminmsgs':[], 
                        }
                msglists[da] = mlist

        return mlist

    def clearRealExtMsgs(self, sa, da=None):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        clear out extended messages metadata.

        if da == None, this clears *all* message data for a given source address

        returns whether the thing deleted exists previously
        * if da == None, returns whether the sa had anything previously
        * otherwise, if the list 
        '''
        exists = False
        if da != None:
            msglists = self._RealExtMsgParts.get(sa)
            exists = bool(msglists != None and len(msglists))
            self._RealExtMsgParts[sa] = {}
            return exists

        msglists = self._RealExtMsgParts.get(sa)
        if msglists == None:
            msglists = {}
            self._RealExtMsgParts[sa] = msglists

        mlist = msglists.get(da, {'length':0})
        msglists[da] = {'length':0, 'msgs':[], 'type':None, 'adminmsgs':[]}
        return bool(mlist['length'])

    def saveRealExtMsg(self, idx, ts, sa, da, pgn, msg, tptype, lastidx):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        store a TP message.
        '''
        # FIXME: do we need thread-safety wrappers here?
        msglist = self._RealExtMsgs.get((sa,da))
        if msglist == None:
            msglist = []
            self._RealExtMsgs[(sa,da)] = msglist

        msglist.append((idx, ts, sa, da, pgn, msg, tptype, lastidx))

    # This is for the pretty printing stuff...
    def getExtMsgs(self, sa, da):
        '''
        returns a message list for a given source and destination (sa, da)

        if no list exists for this pairing, one is created and an empty list is returned
        '''
        msglists = self._reprExtMsgs.get(sa)
        if msglists == None:
            msglists = {}
            self._reprExtMsgs[sa] = msglists

        mlist = msglists.get(da)
        if mlist == None:
            mlist = {'length':0, 'msgs':[], 'type':None, 'adminmsgs':[]}
            msglists[da] = mlist

        return mlist

    def clearExtMsgs(self, sa, da=None):
        '''
        clear out extended messages metadata.

        if da == None, this clears *all* message data for a given source address

        returns whether the thing deleted exists previously
        * if da == None, returns whether the sa had anything previously
        * otherwise, if the list 
        '''
        exists = False
        if da != None:
            msglists = self._reprExtMsgs.get(sa)
            exists = bool(msglists != None and len(msglists))
            self._reprExtMsgs[sa] = {}
            return exists

        msglists = self._reprExtMsgs.get(sa)
        if msglists == None:
            msglists = {}
            self._reprExtMsgs[sa] = msglists

        mlist = msglists.get(da, {'length':0})
        msglists[da] = {'length':0, 'msgs':[], 'type':None, 'adminmsgs':[]}
        return bool(mlist['length'])

    def addID(self, newid):
        if newid not in self.myIDs:
            self.myIDs.append(newid)

    def delID(self, curid):
        if curid in self.myIDs:
            self.myIDs.remove(curid)

    def J1939xmit(self, pf, ps, sa, data, prio=6, edp=0, dp=0):
        arbid = emitArbid(prio, edp, dp, pf, ps, sa)
        # FIXME: make this choose _tp if len(data) > 8
        return self.CANxmit(arbid, data, extflag=1)

    def J1939xmit_tp(self, da, sa, pgn2, pgn1, pgn0, message, prio=6, edp=0, dp=0):

        msgs = ['%c'%(x+1) + message[x*7:(x*7)+7] for x in range((len(message)+6)/7)]
        if len(msgs) > 255:
            raise Exception("J1939xmit_tp: attempt to send message that's too large")

        cm_msg = struct.pack('<BHBBBBB', CM_RTS, len(message), len(msgs), 0xff, 
                pgn2, pgn1, pgn0)
        self.J1939xmit(PF_TP_CM, da, sa, cm_msg, prio=prio)
        time.sleep(.01)  # hack: should watch for CM_CTS
        for msg in msgs:
            self.J1939xmit(PF_TP_DT, da, sa, msg, prio=prio)

        # hack: should watch for CM_EOM


    def recvRealExtMsg(self, sa, da, pgn2, pgn1, pgn0, start_msg=None, block=True, timeout=1):
        '''
        Find the first recv'd message from the J1939tp stack after start_msg, for PGN made up of pgn2,pgn1,pgn0
        wait until timeout seconds have lapsed

        if start_msg == None, returns the next message since last J1939recv/tp
        '''
        starttime = time.time()
        if start_msg == None:
            start_msg = self._last_recv_idx + 1
            self.log( "resuming last recv'd index: %d" % start_msg)

        count = 0
        while (count==0 or (block and time.time()-starttime < timeout)):
            #sys.stderr.write('.')
            count += 1
            msgs = self._RealExtMsgs.get((sa, da))
            if msgs == None or not len(msgs):
                #print "no message for %.2x -> %.2x" % (sa, da)
                continue

            if msgs[-1][0] < start_msg:
                self.log("last msg before start_msg %r  %r" % (msgs[-1][0],start_msg), 2)
                #sys.stderr.write('.')
                continue

            for midx in range(len(msgs)):
                msg = msgs[midx]
                midx = msg[0]
                mpgn = msg[4]
                mlastidx = msg[7]
                #print "     %r ?>= %r" % (midx, start_msg)
                #print "     %r ?= %r" % (mpgn, (pgn2, pgn1, pgn0))
                if midx < start_msg:
                    continue
                if mpgn != (pgn2, pgn1, pgn0):
                    continue

                #print "success! %s" % repr(msg)
                #print "setting last recv'd index: %d" % mlastidx
                self._last_recv_idx = mlastidx
                ##FIXME:  make this threadsafe
                #msgs.pop(midx)
                return msg


        raise TimeoutException('recvRealExtMsg: Timeout waiting for message from: 0x%.2x -> 0x%.2x PGN: %.2x%.2x%.2x' % \
                (sa, da, pgn2,pgn1,pgn0))

    def J1939recv_tp(self, pgn2, pgn1, pgn0, sa=0x0, da=0xf9, msgcount=1, timeout=1, advfilters=[], start_msg=None):
        if start_msg == None:
            start_msg = self._last_recv_idx + 1

        self.log("J1939recv_tp: Searching for response at or after msg idx: %d" % start_msg)
        msg = self.recvRealExtMsg(sa, da, pgn2, pgn1, pgn0, start_msg, timeout=timeout)
        if msg == None:
            return None

        out = msg[5]
        return out

    def J1939recv(self, msgcount=1, timeout=1, advfilters=[], start_msg=None):
        out = []

        if start_msg == None:
            start_msg = self._last_recv_idx + 1
            self.log('start_msg: %d' % start_msg)

        for msg in self.filterCanMsgs(start_msg=start_msg, advfilters=advfilters, tail=True, maxsecs=timeout):
            #(idx, ts, arbid, data) = msg
            out.append(msg)
            self._last_recv_idx = msg[0]

            if len(out) >= msgcount:
                return out

        return out

    def J1939xmit_recv(self, pf, ps, sa, data, recv_arbid=None, recv_count=1, prio=6, edp=0, dp=0, timeout=1, advfilters=[]):
        msgidx = self.getCanMsgCount()

        res = self.J1939xmit(pf, ps, sa, data, prio, edp, dp)
        res = self.J1939recv(recv_count, timeout, advfilters, start_msg=msgidx)

        return res


    def J1939_Request(self, rpf, rda_ge=0, redp=0, rdp=0, da=0xff, sa=0xfe, prio=0x6, recv_count=255, timeout=2, advfilters=[]):
        pgnbytes = [rda_ge, rpf, redp<<1 | rdp]
        data = ''.join([chr(x) for x in pgnbytes])
        data += '\xff' * (8-len(data))

        if not len(advfilters):
            advfilters = 'pf in (0x%x, 0xeb, 0xec)' % rpf

        if recv_count == 0:
            return

        # FIXME: this is only good for short requests... anything directed is likely to send back a TP message
        msgs = self.J1939xmit_recv(PF_RQST, da, sa, data, recv_count=recv_count, prio=prio, timeout=timeout, advfilters=advfilters)
        return msgs

    def J1939_ClaimAddress(self, addr, name=0x4040404040404040, prio=6):
        data = struct.pack(">Q", name)
        out = self.J1939xmit_recv(pf=PF_ADDRCLAIM, ps=0xff, sa=addr, data=data, recv_count=10, prio=prio<<2, timeout=2, advfilters=['pf==0xee'])
        self.addID(addr)
        return out

    def J1939_ArpAddresses(self):
        '''
        Sends a request for all used addresses... not fully tested
        '''
        #idx = self.getCanMsgCount()
        msgs = self.J1939_Request(PF_ADDRCLAIM, recv_count=255, advfilters=['pf==0xee'])

        '''
        # FIXME: these are way too loose, for discovery only. tighten down.
        recv_filters = [
                'pf < 0xf0',
                #'pf == 0xee',
                ]

        msgs = self.J1939recv(msgcount=200, timeout=3, advfilters=recv_filters, start_msg=idx)
        '''
        for msg in msgs:
            try:
                msgrepr = self._reprCanMsg(*msg)
                if msgrepr != cancat.DONT_PRINT_THIS_MESSAGE:
                    print msgrepr
            except Exception, e:
                print e
        '''
        example (from start of ECU):
        00000000 1545142410.990 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request
        00000001 1545142411.077 pri/edp/dp: 6/0/0, PG: ee ff  Source: 00  Len: 08, Data: 4cca4d0100000000    Address Claim: id: 0xdca4c mfg: Cummins Inc (formerly Cummins Engine Co) Columbus, IN USA
    
        currently ours:
        00001903 1545142785.127 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request

        '''


