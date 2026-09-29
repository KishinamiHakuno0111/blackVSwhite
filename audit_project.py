from pathlib import Path
import sys, re, json, subprocess, os, hashlib, shutil, xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(os.environ.get('BLACK_WHITE_LEGACY_ROOT', Path(__file__).parent / 'legacy' / 'Black and White Chess')).resolve()
OUT = Path(__file__).parent / 'audit_artifacts'
OUT.mkdir(exist_ok=True)
NS = {'m': 'http://schemas.microsoft.com/developer/msbuild/2003'}

def decode(p):
    b = p.read_bytes()
    if b.startswith(b'\xff\xfe'):
        return b.decode('utf-16')
    try:
        return b.decode('utf-8-sig')
    except UnicodeDecodeError:
        return b.decode('gbk', errors='replace')

def vcenv():
    setup = r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat'
    result = subprocess.run(f'cmd.exe /d /s /c ""{setup}" >nul && set"', capture_output=True)
    env = os.environ.copy()
    for line in result.stdout.decode('mbcs', errors='replace').splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            env[k] = v
    return env

def audit():
    env = vcenv()
    results = []
    sln = decode(ROOT / 'Black and White Chess.sln')
    for n, p in enumerate(sorted(ROOT.rglob('*.vcxproj'))):
        tree = ET.parse(p)
        sources = [p.parent / x.get('Include') for x in tree.findall('.//m:ClCompile[@Include]', NS)]
        target = OUT / f'build_{n:02d}'
        target.mkdir(exist_ok=True)
        cmd = [shutil.which('cl.exe', path=env.get('Path', env.get('PATH'))), '/nologo', '/EHsc', '/W3', '/Od', '/D_CRT_SECURE_NO_WARNINGS', '/source-charset:.936', '/execution-charset:.936',
               *[str(s) for s in sources], f'/Fe{target / "program.exe"}', f'/Fo{target}\\']
        proc = subprocess.run(cmd, env=env, cwd=target, capture_output=True, timeout=45)
        log = proc.stdout.decode('mbcs', errors='replace') + proc.stderr.decode('mbcs', errors='replace')
        (target / 'build.log').write_text(log, encoding='utf-8')
        hist = p.parent / 'Release' / f'{p.stem}.log'
        hlog = decode(hist) if hist.exists() else ''
        row = dict(project=p.parent.name, in_solution=str(p.relative_to(ROOT)) in sln,
                   sources=[str(s.relative_to(ROOT)) for s in sources],
                   references=[x.get('Include') for x in tree.findall('.//m:ProjectReference', NS)],
                   result=proc.returncode, output=str(target),
                   errors=[l.strip() for l in log.splitlines() if 'error ' in l],
                   historical_errors=[l.strip() for l in hlog.splitlines() if re.search(r'(?:fatal )?error [CL]', l)])
        results.append(row)
        print(row['project'], 'OK' if proc.returncode == 0 else 'FAIL', '; '.join(row['errors'][:2]), flush=True)
    (OUT / 'build_results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    files = [dict(path=str(p.relative_to(ROOT)), size=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in ROOT.rglob('*') if p.is_file()]
    (OUT / 'source_inventory.json').write_text(json.dumps(files, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    audit()
