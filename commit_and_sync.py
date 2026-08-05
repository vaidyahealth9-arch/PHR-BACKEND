import os
import subprocess

REPOS = [
    r"c:\Users\ranju\OneDrive\Documents\GitHub\Halelabs(Vaidya)\limsAndPhr\Version2\lims\lims-backend",
    r"c:\Users\ranju\OneDrive\Documents\GitHub\Halelabs(Vaidya)\limsAndPhr\Version2\lims\lims-web",
    r"c:\Users\ranju\OneDrive\Documents\GitHub\Halelabs(Vaidya)\limsAndPhr\Version2\phr\phr_backend1",
    r"c:\Users\ranju\OneDrive\Documents\GitHub\Halelabs(Vaidya)\limsAndPhr\Version2\phr\phr_frontend"
]

COMMIT_MSG = "feat(auth): fix Firebase OTP integration, sync environment configuration and auth endpoints"

def run_cmd(repo, args):
    res = subprocess.run(args, cwd=repo, capture_output=True, text=True, shell=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def sync_repo(repo):
    name = os.path.basename(repo)
    print(f"\n=======================================================")
    print(f" SYNCING REPOSITORY: {name}")
    print(f"=======================================================")
    
    # 1. Check status
    out, err, code = run_cmd(repo, ["git", "status", "-s"])
    if out:
        print(f"Staging and committing local changes in {name}...")
        run_cmd(repo, ["git", "add", "."])
        out_c, err_c, code_c = run_cmd(repo, ["git", "commit", "-m", f'"{COMMIT_MSG}"'])
        print(out_c or err_c)
    else:
        print("No uncommitted changes on current branch.")
        
    # Get current active branch (usually main)
    curr_branch, _, _ = run_cmd(repo, ["git", "branch", "--show-current"])
    if not curr_branch:
        curr_branch = "main"
        
    print(f"Current branch: {curr_branch}")
    
    # 2. Check out development branch (create if doesn't exist)
    out_dev, err_dev, code_dev = run_cmd(repo, ["git", "checkout", "development"])
    if code_dev != 0:
        print("Creating local 'development' branch...")
        run_cmd(repo, ["git", "checkout", "-b", "development"])
        
    # Merge curr_branch into development
    print(f"Merging {curr_branch} into development...")
    out_m, err_m, code_m = run_cmd(repo, ["git", "merge", curr_branch, "--no-ff", "-m", f'"Merge {curr_branch} into development"'])
    print(out_m or err_m)
    
    # Push development
    print("Pushing 'development' to origin...")
    out_pd, err_pd, code_pd = run_cmd(repo, ["git", "push", "origin", "development"])
    print(out_pd or err_pd)
    
    # Switch back to main
    run_cmd(repo, ["git", "checkout", "main"])
    print(f"Merging development into main...")
    out_mm, err_mm, _ = run_cmd(repo, ["git", "merge", "development", "-m", '"Merge development into main"'])
    print(out_mm or err_mm)
    
    # Push main
    print("Pushing 'main' to origin...")
    out_pm, err_pm, code_pm = run_cmd(repo, ["git", "push", "origin", "main"])
    print(out_pm or err_pm)
    
    print(f"✅ {name} successfully synced and pushed to main and development!")

def main():
    for repo in REPOS:
        sync_repo(repo)

if __name__ == "__main__":
    main()
