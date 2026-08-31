import struct,sys
def parse(p):
    d=open(p,'rb').read()
    assert d[:4]==b'\x7fELF'
    e_shoff,=struct.unpack_from('<I',d,0x20); e_shentsize,=struct.unpack_from('<H',d,0x2E)
    e_shnum,=struct.unpack_from('<H',d,0x30); e_shstrndx,=struct.unpack_from('<H',d,0x32)
    secs=[]
    for i in range(e_shnum):
        o=e_shoff+i*e_shentsize
        name,typ,flags,addr,off,size,link,info,align,entsize=struct.unpack_from('<10I',d,o)
        secs.append(dict(name=name,typ=typ,off=off,size=size,link=link,entsize=entsize))
    shstr=secs[e_shstrndx]
    def sname(n):
        b=d[shstr['off']+n:]; return b[:b.index(b'\0')].decode()
    for s in secs: s['n']=sname(s['name'])
    by={s['n']:s for s in secs}
    out={'needed':[],'soname':None,'defined':[],'undef':[]}
    dyn=by.get('.dynamic'); dstr=by.get('.dynstr')
    def sstr(o):
        b=d[dstr['off']+o:]; return b[:b.index(b'\0')].decode()
    if dyn and dstr:
        for i in range(dyn['size']//8):
            tag,val=struct.unpack_from('<iI',d,dyn['off']+i*8)
            if tag==1: out['needed'].append(sstr(val))
            elif tag==14: out['soname']=sstr(val)
            elif tag==0: break
    ds=by.get('.dynsym')
    if ds and dstr:
        for i in range(ds['size']//16):
            o=ds['off']+i*16
            nm,value,size,info,other,shndx=struct.unpack_from('<IIIBBH',d,o)
            if nm==0: continue
            n=sstr(nm)
            (out['undef'] if shndx==0 else out['defined']).append(n)
    return out
a=parse(sys.argv[1])
print('SONAME:',a['soname'])
print('DT_NEEDED (%d):'%len(a['needed']))
for x in sorted(a['needed']): print('  ',x)
print('导出符号 (%d):'%len(a['defined']))
for x in sorted(a['defined'])[:20]: print('  ',x)
print('未解析符号 (%d):'%len(a['undef']))
for x in sorted(a['undef'])[:15]: print('  ',x)
