import pathlib,json,urllib.request,urllib.error,hashlib,datetime,shutil,xml.etree.ElementTree as ET
E=pathlib.Path(r'C:\Plugin\BioNexus\review\spatialwarrant-run-01\00_plan\S1-to-S2-entry-evidence.v1')
def save(n,o):
    assert shutil.disk_usage('C:\\').free>=20*1024**3
    with (E/n).open('x',encoding='utf-8') as f:json.dump(o,f,ensure_ascii=True,indent=2)
ret=json.loads((E/'PMC-plugin-stdout.v1.json').read_text(encoding='utf-8'));url=ret['records'][0]['xml_url']
request={'method':'GET','url':url,'timeout_seconds':30,'headers':{'User-Agent':'SpatialWarrant-S1-entry-review/1.0'},'purpose':'Identity and supplementary-source provenance only; no biological analysis','created':datetime.datetime.now(datetime.timezone.utc).isoformat()}
save('PMC-XML-request.v1.json',request)
try:
    with urllib.request.urlopen(urllib.request.Request(url,headers=request['headers']),timeout=30) as res:
        b=res.read(3*1024**2);rec={'http_status':res.status,'resolved_url':res.url,'headers':dict(res.headers),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'md5':hashlib.md5(b).hexdigest()}
    with (E/'PMC9044823.1.source.v1.xml').open('xb') as f:f.write(b)
    save('PMC-XML-return.v1.json',rec)
    root=ET.fromstring(b);links=[]
    for x in root.iter():
        for k,v in x.attrib.items():
            if k.endswith('href') and ('supp' in v.lower() or x.tag in ['supplementary-material','media']):links.append({'tag':x.tag,'href':v,'text':''.join(x.itertext())[:500]})
    text=' '.join(root.itertext());findings=[]
    for term in ['CID4290A','orig.ident','three tissue regions','Supplementary Table 1']:
        pos=0;hits=[]
        while (pos:=text.find(term,pos))>=0: hits.append(text[max(0,pos-130):pos+200]);pos+=len(term)
        findings.append({'term':term,'hits':hits})
    save('PMC-XML-identity-search.v1.json',{'source_file':'PMC9044823.1.source.v1.xml','links':links,'findings':findings})
    print(json.dumps({'return':rec,'links':links,'findings':findings}))
except Exception as ex:
    err={'type':type(ex).__name__,'message':str(ex)}
    if isinstance(ex,urllib.error.HTTPError):
        err['status']=ex.code
        with (E/'PMC-XML-error-body.v1.bin').open('xb') as f:f.write(ex.read())
    save('PMC-XML-failure.v1.json',err);print(json.dumps(err))
