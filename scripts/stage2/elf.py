import struct
def sections(d):
    is64 = d[4]==2
    if is64:
        e_shoff,=struct.unpack('<Q',d[40:48]); e_shentsize,=struct.unpack('<H',d[58:60])
        e_shnum,=struct.unpack('<H',d[60:62]); e_shstrndx,=struct.unpack('<H',d[62:64])
    else:
        e_shoff,=struct.unpack('<I',d[32:36]); e_shentsize,=struct.unpack('<H',d[46:48])
        e_shnum,=struct.unpack('<H',d[48:50]); e_shstrndx,=struct.unpack('<H',d[50:52])
    secs=[]
    for i in range(e_shnum):
        o=e_shoff+i*e_shentsize
        if is64:
            name,typ,flags,addr,off,size,link,info,align,entsize=struct.unpack('<IIQQQQIIQQ',d[o:o+64])
        else:
            name,typ,flags,addr,off,size,link,info,align,entsize=struct.unpack('<10I',d[o:o+40])
        secs.append(dict(name=name,typ=typ,off=off,size=size,link=link,entsize=entsize))
    shstr=secs[e_shstrndx]
    for s in secs:
        b=d[shstr['off']+s['name']:]; s['sname']=b[:b.index(b'\0')].decode(errors='replace')
    return secs,is64
def cstr(d,base,off):
    b=d[base+off:]; return b[:b.index(b'\0')].decode(errors='replace')
def dynsyms(path):
    """returns (defined:set, undefined:set, needed:list, soname)"""
    d=open(path,'rb').read()
    if d[:4]!=b'\x7fELF': return None
    secs,is64=sections(d)
    by={s['sname']:s for s in secs}
    if '.dynsym' not in by or '.dynstr' not in by: return None
    sym,strt=by['.dynsym'],by['.dynstr']
    defined,undef=set(),set()
    ent=24 if is64 else 16
    for i in range(0,sym['size'],ent):
        o=sym['off']+i
        if is64:
            nm,info,other,shndx,value,sz=struct.unpack('<IBBHQQ',d[o:o+24])
        else:
            nm,value,sz,info,other,shndx=struct.unpack('<IIIBBH',d[o:o+16])
        if nm==0: continue
        n=cstr(d,strt['off'],nm)
        (undef if shndx==0 else defined).add(n)
    needed,soname=[],None
    if '.dynamic' in by:
        dy=by['.dynamic']; o=dy['off']; step=16 if is64 else 8
        while o < dy['off']+dy['size']:
            if is64: tag,val=struct.unpack('<qQ',d[o:o+16])
            else:    tag,val=struct.unpack('<iI',d[o:o+8])
            o+=step
            if tag==0: break
            if tag==1: needed.append(cstr(d,strt['off'],val))
            if tag==14: soname=cstr(d,strt['off'],val)
    return defined,undef,needed,soname
