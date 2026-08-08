import os
import subprocess

REPOS = [
    r"c:\Users\ranju\OneDrive\Documents\GitHub\Halelabs(Vaidya)\limsAndPhr\Version2\phr\phr_backend1",
    r"c:\Users\ranju\OneDrive\Documents\GitHub\Halelabs(Vaidya)\limsAndPhr\Version2\phr\phr_frontend"
]

COMMIT_MSG = "fix(auth): resolve local token verification and clear react-query cache on logout"

def run_cmd(repo, args):
    res = subprocess.run(args, cwd=repo, capture_output=True, text=True, shell=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def safe_sync(repo):
    name = os.path.basename(repo)
    print(f"\n=======================================================")
    print(f" SYNCING REPOSITORY: {name}")
    print(f"=======================================================")
    
    # 1. Check local changes on main and commit them
    run_cmd(repo, ["git", "checkout", "main"])
    status_out, _, _ = run_cmd(repo, ["git", "status", "-s"])
    if status_out:
        print(f"Staging and committing local changes in {name} on main...")
        run_cmd(repo, ["git", "add", "."])
        out_c, err_c, _ = run_cmd(repo, ["git", "commit", "-m", f'"{COMMIT_MSG}"'])
        print(out_c or err_c)
        
    # 2. Pull remote main
    print("Pulling remote main...")
    out_pm, err_pm, _ = run_cmd(repo, ["git", "pull", "origin", "main", "--no-rebase", "-X", "ours"])
    print(out_pm or err_pm)
    
    # 3. Push main
    print("Pushing main...")
    out_push_main, err_push_main, _ = run_cmd(repo, ["git", "push", "origin", "main"])
    print(out_push_main or err_push_main)
    
    # 4. Check out development
    print("Checking out development branch...")
    run_cmd(repo, ["git", "checkout", "development"])
    
    # Pull remote development
    print("Pulling remote development...")
    out_pd, err_pd, _ = run_cmd(repo, ["git", "pull", "origin", "development", "--no-rebase", "-X", "ours"])
    print(out_pd or err_pd)
        
    # 5. Merge main into development
    print("Merging main into development...")
    out_m, err_m, _ = run_cmd(repo, ["git", "merge", "main", "--no-ff", "-m", f'"Merge main into development"'])
    print(out_m or err_m)
    
    # Push development
    print("Pushing 'development' to origin...")
    out_push_dev, err_push_dev, _ = run_cmd(repo, ["git", "push", "origin", "development"])
    print(out_push_dev or err_push_dev)
    
    # Go back to main
    run_cmd(repo, ["git", "checkout", "main"])
    print(f"DONE: {name} synced successfully!")

def main():
    for repo in REPOS:
        safe_sync(repo)

if __name__ == "__main__":
    main()
