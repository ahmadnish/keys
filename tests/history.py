from pathlib import Path
import subprocess,tempfile,os
base=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as home:
 env=dict(os.environ,HOME=home);env.pop('INPUTRC',None);env.pop('XDG_STATE_HOME',None)
 rc=Path(home)/'.inputrc';original=b'# original with no trailing newline\n"\\e[A": previous-history'
 rc.write_bytes(original)
 def run(*args,ok=True):
  r=subprocess.run(['bash',str(base/'history.sh'),*args],env=env,capture_output=True,text=True)
  assert (r.returncode==0)==ok,(r.stdout,r.stderr)
  return r
 run();installed=rc.read_bytes();run();assert installed==rc.read_bytes()
 assert original in installed
 run('--undo');assert rc.read_bytes()==original
 assert not (Path(home)/'.local/state/ahmadnish-keys').exists()
 run();rc.write_bytes(rc.read_bytes()+b'# user added\n');run('--undo',ok=False)
 assert rc.read_bytes().endswith(b'# user added\n')
 rc.write_bytes(installed);run('--undo');assert rc.read_bytes()==original
 rc.unlink();run();run('--undo');assert not rc.exists()
 # Preserve a user-owned symlink and its target.
 target=Path(home)/'readline-settings';target.write_bytes(original);rc.symlink_to(target)
 run();assert rc.is_symlink();run('--undo');assert rc.is_symlink() and target.read_bytes()==original
 print('PASS: history install, repeat, exact undo, edit protection, absent file and symlink restoration')
 # Verify activation and rollback in an interactive Bash process.
 rc.unlink();rc.write_bytes(original)
 command=f'. "{base}/history.sh"; bind -p | grep history-search-backward; . "{base}/history.sh" --undo; bind -p | grep previous-history'
 result=subprocess.run(['bash','--noprofile','--norc','-ic',command],env=env,capture_output=True,text=True)
 print(result.stdout)
 assert result.returncode==0,(result.stdout,result.stderr)
 assert rc.read_bytes()==original
print('PASS: immediate Bash activation/undo')
