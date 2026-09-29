from pathlib import Path
from audit_project import OUT
import json, subprocess, random

def flips(b,p,x,y):
    if b[x][y]!=2:return []
    result=[]
    for dx in [-1,0,1]:
        for dy in [-1,0,1]:
            if not dx and not dy:continue
            a,c=x+dx,y+dy;line=[]
            while 1<=a<=10 and 1<=c<=10 and b[a][c]==1-p:
                line.append((a,c));a+=dx;c+=dy
            if line and 1<=a<=10 and 1<=c<=10 and b[a][c]==p:result+=line
    return result

rows=json.loads((OUT/'build_results.json').read_text(encoding='utf-8'))
results=[]
for project in ['human va human','ConsoleApplication1']:
    b=[[2]*12 for _ in range(12)];b[5][5]=b[6][6]=1;b[5][6]=b[6][5]=0
    rng=random.Random(1928);p=0;passes=0;inputs=[];moves=0
    while passes<2:
        options=[(x,y,flips(b,p,x,y)) for x in range(1,11) for y in range(1,11)]
        options=[o for o in options if o[2]]
        if not options:passes+=1;p=1-p;continue
        passes=0
        ai=project=='ConsoleApplication1' and p==1
        x,y,changed=max(options,key=lambda o:len(o[2])) if ai else rng.choice(options)
        if not ai:inputs.append(f'{x} {y}')
        b[x][y]=p
        for a,c in changed:b[a][c]=p
        p=1-p;moves+=1
    black=sum(row.count(0) for row in b);white=sum(row.count(1) for row in b)
    expected='黑棋获得胜利' if black>white else '白棋获得胜利' if white>black else '双方平局'
    row=next(r for r in rows if r['project']==project)
    proc=subprocess.run([str(Path(row['output'])/'program.exe')],input=('\n'.join(inputs)+'\n').encode(),capture_output=True,cwd=OUT/'runtime',timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    text=proc.stdout.decode('gbk',errors='replace')
    (OUT/'runtime'/(project.replace(' ','_')+'_play.stdout')).write_bytes(proc.stdout)
    result=dict(project=project,moves=moves,black=black,white=white,exit_code=proc.returncode,matched_winner=expected in text,normal_end='游戏结束' in text,rejected_move='下错了' in text)
    results.append(result);print(result)
(OUT/'runtime'/'playability_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
