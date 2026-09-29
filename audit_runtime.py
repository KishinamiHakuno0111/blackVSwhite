from audit_project import ROOT, OUT, vcenv
import subprocess, json, shutil, time
from concurrent.futures import ThreadPoolExecutor

HARNESS = r'''
#define main historical_main
#include "LEGACY_SOURCE_PATH"
#undef main
#include <string.h>
int reflegal(int b[12][12], int p, int x, int y) {
 if(x<1||x>10||y<1||y>10||b[x][y]!=2)return 0;
 for(int dx=-1;dx<=1;dx++)for(int dy=-1;dy<=1;dy++) {
  if(!dx&&!dy)continue;
  int a=x+dx,c=y+dy,n=0;
  while(a>=1&&a<=10&&c>=1&&c<=10&&b[a][c]==1-p){a+=dx;c+=dy;n++;}
  if(n&&a>=1&&a<=10&&c>=1&&c<=10&&b[a][c]==p)return 1;
 }
 return 0;
}
void refmove(int b[12][12],int p,int x,int y) {
 for(int dx=-1;dx<=1;dx++)for(int dy=-1;dy<=1;dy++) {
  if(!dx&&!dy)continue;
  int a=x+dx,c=y+dy,n=0;
  while(a>=1&&a<=10&&c>=1&&c<=10&&b[a][c]==1-p){a+=dx;c+=dy;n++;}
  if(n&&a>=1&&a<=10&&c>=1&&c<=10&&b[a][c]==p)
   for(int k=1;k<=n;k++)b[x+k*dx][y+k*dy]=p;
 }
 b[x][y]=p;
}
int main() {
 unsigned int rng=1234567; int moves=0,passes=0,checks=0;
 for(int g=0;g<100;g++) {
  int b[12][12],r[12][12],p=0,pass=0;init(b);memcpy(r,b,sizeof b);
  while(pass<2) {
   int options[100][2],n=0;
   for(int x=1;x<=10;x++)for(int y=1;y<=10;y++) {
    int yes=reflegal(r,p,x,y);checks++;
    if(yes!=isCanGo(p,b,x,y)){printf("FAIL legal\n");return 1;}
    if(yes){options[n][0]=x;options[n++][1]=y;}
   }
   if(confirm(p,b)!=(n>0)){printf("FAIL confirm\n");return 1;}
   if(!n){pass++;passes++;p=1-p;continue;}
   pass=0;rng=rng*1664525u+1013904223u;int idx=rng%n;
   int ret[2]={options[idx][0],options[idx][1]};
   act(p,b,ret);refmove(r,p,ret[0],ret[1]);moves++;
   if(memcmp(b,r,sizeof b)){printf("FAIL act\n");return 1;}
   p=1-p;
  }
  int black=0,white=0;for(int x=1;x<=10;x++)for(int y=1;y<=10;y++){black+=r[x][y]==0;white+=r[x][y]==1;}
  int winner=black>white?0:black<white?1:2;
  if(victory(b)!=winner){printf("FAIL victory\n");return 1;}
 }
 printf("RULES PASS games=100 moves=%d passes=%d legal_checks=%d\n",moves,passes,checks);
 int b[12][12],dest[12][12],points[96][2];
 init(b);for(int x=1;x<=10;x++)for(int y=1;y<=10;y++)b[x][y]=0;
 printf("FIRM all_black black=%d white=%d\n",firm(b,0),firm(b,1));
 for(int x=0;x<12;x++)for(int y=0;y<12;y++)dest[x][y]=-77;
 copy(dest,b);int bad=0;
 for(int x=0;x<12;x++)for(int y=0;y<12;y++)if((x==0||y==0||x==11||y==11)&&dest[x][y]!=b[x][y])bad++;
 printf("COPY border_cells_not_copied=%d\n",bad);
 for(int i=0;i<96;i++){points[i][0]=9;points[i][1]=9;}
 clean(points,3);int changed=0;for(int i=3;i<96;i++)if(points[i][0]==1&&points[i][1]==0)changed++;
 printf("CLEAN reset_entries=%d expected=93\n",changed);
 return 0;
}
'''

def main():
    target=OUT/'runtime'
    target.mkdir(exist_ok=True)
    source = (ROOT / 'Black and White Chess' / 'black and white chess.cpp').as_posix()
    (target/'harness.cpp').write_text(HARNESS.replace('LEGACY_SOURCE_PATH', source),encoding='utf-8')
    env=vcenv()
    cl=shutil.which('cl.exe',path=env.get('Path',env.get('PATH')))
    build=subprocess.run([cl,'/nologo','/EHsc','/O2','/D_CRT_SECURE_NO_WARNINGS','/source-charset:.936','/execution-charset:.936',str(target/'harness.cpp'),f'/Fe{target / "harness.exe"}',f'/Fo{target}\\'],env=env,cwd=target,capture_output=True)
    (target/'harness_build.log').write_bytes(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError('harness compile failed')
    result=subprocess.run([str(target/'harness.exe')],capture_output=True,timeout=15,cwd=target)
    (target/'harness_result.txt').write_bytes(result.stdout+result.stderr)
    print(result.stdout.decode('ascii'),flush=True)
    rows=json.loads((OUT/'build_results.json').read_text(encoding='utf-8'))
    selected={'Black and White Chess','ConsoleApplication2','superAI','superAI2.0','test','test2','test3','test4'}
    def run(row):
        name=row['project']; t=time.monotonic()
        with (target/(name.replace(' ','_')+'.stdout')).open('wb') as out:
            p=subprocess.Popen([str(Path(row['output'])/'program.exe')],cwd=target,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            try: code=p.wait(timeout=8);status='exited'
            except subprocess.TimeoutExpired:p.kill();p.wait();code=p.returncode;status='timeout_8s'
        output=(target/(name.replace(' ','_')+'.stdout')).read_bytes().decode('gbk',errors='replace')
        row=dict(project=name,status=status,exit_code=code,seconds=round(time.monotonic()-t,3),output_bytes=len(output.encode('utf-8')),tail=output[-400:])
        print(name,status,hex(code & 0xffffffff),row['tail'][-100:].replace('\n',' '),flush=True)
        return row
    from pathlib import Path
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(run,[r for r in rows if r['project'] in selected]))
    (target/'runtime_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
