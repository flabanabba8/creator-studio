"""Make actual presentation graphics from explicit data, never fabricated research."""
import hashlib,json,math,os,textwrap,uuid
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def font(size,bold=False):
    try:return ImageFont.truetype('DejaVuSans-Bold.ttf'if bold else'DejaVuSans.ttf',size)
    except OSError:return ImageFont.load_default(size=size)

def label(value,name,maxlen=160):
    if not isinstance(value,str)or not value.strip()or len(value)>maxlen or any(ord(c)<32 for c in value):raise ValueError('Use a short printable '+name)
    return value.strip()

def number(value):
    if isinstance(value,bool)or not isinstance(value,(int,float))or not math.isfinite(value):raise ValueError('Chart values must be finite actual numbers')
    return value

def make_visual(root,kind,title,data,provenance):
    if kind not in ('bar','line','table','flowchart','cycle'):raise ValueError('Choose bar, line, table, flowchart or cycle; use native image generation for artwork')
    if not isinstance(data,dict)or len(json.dumps(data))>100000:raise ValueError('Use bounded explicit graphic data')
    if not isinstance(provenance,dict)or provenance.get('kind')not in('sourced','measurement','illustrative'):raise ValueError('Label data as sourced, measured or illustrative; no invented benchmark claims')
    note=label(provenance.get('note'),'data/source note',180);title=label(title,'title',100)
    image=Image.new('RGB',(1920,1080),'#f0f5fb');d=ImageDraw.Draw(image);d.rectangle((0,0,1920,145),fill='#13283e');heading_size=49
    while heading_size>34 and d.textlength(title,font=font(heading_size,True))>1790:heading_size-=2
    if d.textlength(title,font=font(heading_size,True))>1790:raise ValueError('Shorten this graphic heading for readable display')
    d.text((65,40),title,font=font(heading_size,True),fill='white')
    def text_at(x,y,value,width,size=28,maxlines=2,fill='#17374e'):
        lines=[];line='';f=font(size)
        for word in str(value).split():
            candidate=(line+' '+word).strip()
            if d.textlength(candidate,font=f)>width and line:lines.append(line);line=word
            else:line=candidate
        if line:lines.append(line)
        if len(lines)>maxlines or any(d.textlength(x,font=f)>width for x in lines):raise ValueError('Graphic text does not fit; shorten labels or split the graphic')
        for i,line in enumerate(lines):d.text((x,y+i*(size+7)),line,font=f,fill=fill)
    def best(value,width,height,hi=52,lo=26,bold=False):
        for size in range(hi,lo-1,-2):
            f=font(size,bold);lines=[];line=''
            for word in str(value).split():
                candidate=(line+' '+word).strip()
                if d.textlength(candidate,font=f)>width and line:lines.append(line);line=word
                else:line=candidate
            if line:lines.append(line)
            if all(d.textlength(x,font=f)<=width for x in lines)and len(lines)*(size+10)<=height:return size,lines,f
        raise ValueError('Graphic text does not fit; shorten labels or split the graphic')
    def fill_text(x,y,w,h,value,hi=52,lo=26,fill='#17374e',bold=False,size=None):
        size,lines,f=best(value,w,h,hi if size is None else size,lo if size is None else size,bold);total=len(lines)*(size+10)-10
        for i,line in enumerate(lines):d.text((x,y+(h-total)/2+i*(size+10)),line,font=f,fill=fill)
        return size
    if kind=='bar':
        names=data.get('labels');vals=data.get('values')
        if not isinstance(names,list)or not isinstance(vals,list)or len(names)!=len(vals)or not 1<=len(vals)<=10:raise ValueError('Bar chart needs1–10matched labels/values')
        names=[label(x,'bar label',80)for x in names];vals=[number(x)for x in vals];lo=min(0,min(vals));hi=max(0,max(vals));hi=lo+1 if hi==lo else hi
        left,right,top,bottom=480,1740,210,920
        x=lambda v:left+(v-lo)/(hi-lo)*(right-left)
        d.line((x(0),top,x(0),bottom),fill='#8196ab',width=3)
        for i,(name,value)in enumerate(zip(names,vals)):
            y=top+i*(bottom-top)/len(vals);h=min(48,(bottom-top)/len(vals)-15);text_at(65,y,name,380,26,2);a,b=sorted((x(0),x(value)));d.rectangle((a,y+9,max(a+2,b),y+h),fill='#13879a');d.text((min(right+15,max(a,b)+12),y+8),f'{value:g}',font=font(26,True),fill='#17374e')
        for j in range(5):
            v=lo+(hi-lo)*j/4;d.text((x(v)-18,950),f'{v:.4g}',font=font(22),fill='#405a72')
    elif kind=='line':
        vals=data.get('values');xs=data.get('x')
        if not isinstance(vals,list)or not 2<=len(vals)<=40:raise ValueError('Line chart needs2–40data points')
        vals=[number(v)for v in vals];xs=list(range(len(vals)))if xs is None else xs
        if not isinstance(xs,list)or len(xs)!=len(vals):raise ValueError('X coordinates must match values')
        xs=[number(x)for x in xs]
        if any(a>=b for a,b in zip(xs,xs[1:])):raise ValueError('X coordinates must increase; unequal values keep their actual spacing')
        lo=min(0,min(vals));hi=max(vals);hi=lo+1 if hi==lo else hi;left,right,top,bottom=160,1770,220,915
        x=lambda v:left+(v-xs[0])/(xs[-1]-xs[0])*(right-left)
        y=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
        for j in range(5):
            v=lo+(hi-lo)*j/4;yy=y(v);d.line((left,yy,right,yy),fill='#d3e0eb',width=2);d.text((65,yy-13),f'{v:.4g}',font=font(22),fill='#405a72')
        points=[(x(a),y(b))for a,b in zip(xs,vals)];d.line(points,fill='#13879a',width=6)
        for a,b in points:d.ellipse((a-7,b-7,a+7,b+7),fill='#e17d68')
        step=max(1,len(xs)//8)
        for j in range(0,len(xs),step):d.text((x(xs[j])-14,945),f'{xs[j]:g}',font=font(22),fill='#405a72')
    elif kind=='table':
        columns=data.get('columns');rows=data.get('rows')
        if not isinstance(columns,list)or not 1<=len(columns)<=6 or not isinstance(rows,list)or not 1<=len(rows)<=8:raise ValueError('Use1–6columns and1–8rows; split larger tables')
        columns=[label(x,'column title',80)for x in columns]
        if any(not isinstance(row,list)or len(row)!=len(columns)for row in rows):raise ValueError('Every row must match the column count')
        left,top,width,height=60,185,1800,780;cw=width/len(columns);rh=height/(len(rows)+1)
        for row in rows:
            for value in row:
                if not isinstance(value,(str,int,float))or isinstance(value,bool):raise ValueError('Table cells must contain printable text/numbers')
        size=min(best(str(v),cw-40,rh-20,46,26,r==0)[0]for r,row in enumerate([columns]+rows)for v in row)  # one text size for the whole table, as large as every cell allows
        for r,row in enumerate([columns]+rows):
            for c,value in enumerate(row):
                xx=left+c*cw;yy=top+r*rh;d.rectangle((xx,yy,xx+cw-4,yy+rh-4),fill='#d5e8ef'if r==0 else('white'if r%2 else'#e5edf6'));fill_text(xx+20,yy+4,cw-40,rh-12,str(value),size=size,bold=r==0)
    elif kind=='cycle':
        nodes=data.get('nodes')
        if not isinstance(nodes,list)or not 3<=len(nodes)<=10 or any(not isinstance(n,dict)for n in nodes):raise ValueError('A cycle needs 3-10 nodes in order; the last one leads back to the first')
        names=[label(n.get('label'),'node label',100)for n in nodes];k=len(names)
        cx,cy,rx,ry=960,585,690,320;bw,bh=440,125
        boxes=[]
        for i in range(k):
            a=-math.pi/2+2*math.pi*i/k;x=cx+rx*math.cos(a);y=cy+ry*math.sin(a);boxes.append((x-bw/2,y-bh/2,x+bw/2,y+bh/2))
        size=min(best(t,bw-40,bh-24,40,26,True)[0]for t in names)
        def clip2(box,toward):
            mx,my=(box[0]+box[2])/2,(box[1]+box[3])/2;dx,dy=toward[0]-mx,toward[1]-my
            t=min((box[2]-box[0])/2/abs(dx)if dx else 1e9,(box[3]-box[1])/2/abs(dy)if dy else 1e9);return(mx+dx*t,my+dy*t)
        for i in range(k):
            A,B=boxes[i],boxes[(i+1)%k];ca=((A[0]+A[2])/2,(A[1]+A[3])/2);cb=((B[0]+B[2])/2,(B[1]+B[3])/2)
            start=clip2(A,cb);end=clip2(B,ca);d.line((start,end),fill='#4c6c87',width=7);ang=math.atan2(end[1]-start[1],end[0]-start[0])
            d.polygon([end,(end[0]-30*math.cos(ang-.45),end[1]-30*math.sin(ang-.45)),(end[0]-30*math.cos(ang+.45),end[1]-30*math.sin(ang+.45))],fill='#4c6c87')
        for i,box in enumerate(boxes):
            d.rounded_rectangle(box,radius=22,fill='white',outline='#13879a' if i else '#e17d68',width=5);fill_text(box[0]+20,box[1]+8,bw-40,bh-16,names[i],size=size,bold=True)
    else:
        nodes=data.get('nodes');edges=data.get('edges')
        if not isinstance(nodes,list)or not 1<=len(nodes)<=12 or not isinstance(edges,list)or len(edges)>24:raise ValueError('Use1–12nodes and up to24directed edges')
        ids=[label(n.get('id'),'node ID',40)for n in nodes if isinstance(n,dict)]
        if len(ids)!=len(nodes)or len(set(ids))!=len(ids):raise ValueError('Node IDs must be unique')
        labels={n['id']:label(n.get('label'),'node label',100)for n in nodes};parents={n:[]for n in ids}
        for edge in edges:
            if not isinstance(edge,dict)or edge.get('from')not in labels or edge.get('to')not in labels:raise ValueError('Edges must use existing nodes')
            parents[edge['to']].append(edge['from'])
        levels={};remaining=set(ids)
        while remaining:
            ready=[n for n in ids if n in remaining and all(p in levels for p in parents[n])]
            if not ready:raise ValueError('Use an acyclic flow; choose a different diagram renderer for cycles')
            for n in ready:levels[n]=max([levels[p]+1 for p in parents[n]]or[0]);remaining.remove(n)
        count=max(levels.values())+1
        if count>6 or any(list(levels.values()).count(i)>4 for i in range(count)):raise ValueError('Split dense flows or use a selected diagram tool; no edges are silently dropped')
        sizes={};boxes={}
        chain=all(len(parents[n])<=1 for n in ids)and all(list(levels.values()).count(i)==1 for i in range(count))and len(edges)==len(ids)-1
        if chain:
            order=sorted(ids,key=lambda n:levels[n]);n_=len(order);cols=n_ if n_<=3 else(2 if n_==4 else(3 if n_<=6 else 4));rows_=math.ceil(n_/cols)
            gx=150 if cols<=3 else 110;gy=110;bw=(1800-(cols-1)*gx)/cols;bh=min(340,(775-(rows_-1)*gy)/rows_)
            for k,nid in enumerate(order):
                r,c=divmod(k,cols)
                if r%2:c=cols-1-c  # snake: the second row runs back so arrows stay short
                boxes[nid]=(60+c*(bw+gx),190+r*(bh+gy),60+c*(bw+gx)+bw,190+r*(bh+gy)+bh)
        else:
            gx=130;bw=(1800-(count-1)*gx)/count;most=max(list(levels.values()).count(i)for i in range(count));gy=40;bh=min(260,(775-(most-1)*gy)/most)
            for level in range(count):
                group=[n for n in ids if levels[n]==level];total=len(group)*bh+(len(group)-1)*gy;y0=190+(775-total)/2
                for j,n in enumerate(group):boxes[n]=(60+level*(bw+gx),y0+j*(bh+gy),60+level*(bw+gx)+bw,y0+j*(bh+gy)+bh)
        size=min(best(labels[n],bw-48,bh-30,52,26,True)[0]for n in ids)
        def clip(box,toward):
            cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2;dx,dy=toward[0]-cx,toward[1]-cy
            t=min((box[2]-box[0])/2/abs(dx)if dx else 1e9,(box[3]-box[1])/2/abs(dy)if dy else 1e9);return(cx+dx*t,cy+dy*t)
        for edge in edges:
            A,B=boxes[edge['from']],boxes[edge['to']];ca=((A[0]+A[2])/2,(A[1]+A[3])/2);cb=((B[0]+B[2])/2,(B[1]+B[3])/2)
            start=clip(A,cb);end=clip(B,ca);d.line((start,end),fill='#4c6c87',width=7);angle=math.atan2(end[1]-start[1],end[0]-start[0])
            d.polygon([end,(end[0]-30*math.cos(angle-.45),end[1]-30*math.sin(angle-.45)),(end[0]-30*math.cos(angle+.45),end[1]-30*math.sin(angle+.45))],fill='#4c6c87')
            if edge.get('label'):text_at((start[0]+end[0])/2-60,(start[1]+end[1])/2-34,label(edge['label'],'edge label',20),150,26,1)
        for n,box in boxes.items():
            d.rounded_rectangle(box,radius=22,fill='white',outline='#13879a',width=5);fill_text(box[0]+24,box[1]+10,box[2]-box[0]-48,box[3]-box[1]-20,labels[n],size=size,bold=True)
    text_at(65,990,provenance['kind'].title()+': '+note,1790,22,2,fill='#405a72')
    root=Path(root)/'visuals';root.mkdir(parents=True,exist_ok=True,mode=0o700);ident=uuid.uuid4().hex;out=root/(ident+'.png');image.save(out);out.chmod(0o600);metadata={'kind':kind,'title':title,'data':data,'provenance':provenance,'dimensions':[1920,1080],'output_path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'notice':'Actual data-driven material, not image-model artwork or proof the source claims are true. Inspect readability in the main session before assembly.'};sidecar=root/(ident+'.json');sidecar.write_text(json.dumps(metadata,indent=2));sidecar.chmod(0o600);return metadata
