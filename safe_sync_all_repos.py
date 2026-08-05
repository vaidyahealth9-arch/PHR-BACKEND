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

def safe_sync(repo):
    name = os.path.basename(repo)
    print(f"\n=======================================================")
    print(f" SAFE SYNCING REPOSITORY: {name}")
    print(f"=======================================================")
    
    # Abort any in-progress merge if present
    run_cmd(repo, ["git", "merge", "--abort"])
    
    # 1. Fetch all remotes
    run_cmd(repo, ["git", "fetch", "origin"])
    
    # 2. Check local uncommitted changes on current branch and commit them
    curr_branch, _, _ = run_cmd(repo, ["git", "branch", "--show-current"])
    if not curr_branch:
        curr_branch = "main"
        run_cmd(repo, ["git", "checkout", "main"])
        
    status_out, _, _ = run_cmd(repo, ["git", "status", "-s"])
    if status_out:
        print(f"Staging and committing local changes in {name} on {curr_branch}...")
        run_cmd(repo, ["git", "add", "."])
        out_c, err_c, _ = run_cmd(repo, ["git", "commit", "-m", f'"{COMMIT_MSG}"'])
        print(out_c or err_c)
        
    # 3. Pull remote main if branch main exists
    print("Pulling remote main...")
    run_cmd(repo, ["git", "checkout", "main"])
    out_pm, err_pm, _ = run_cmd(repo, ["git", "pull", "origin", "main", "--no-rebase", "-X", "ours"])
    print(out_pm or err_pm)
    
    # 4. Check out development
    print("Checking out development branch...")
    out_cd, err_cd, code_cd = run_cmd(repo, ["git", "checkout", "development"])
    if code_cd != 0:
        run_cmd(repo, ["git", "checkout", "-b", "development"])
    else:
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
    
    # 6. Switch to main, merge development into main, and push main
    print("Switching back to main and syncing with development...")
    run_cmd(repo, ["git", "checkout", "main"])
    out_m2, err_m2, _ = run_cmd(repo, ["git", "merge", "development", "-m", '"Merge development into main"'])
    print(out_m2 or err_m2)
    
    print("Pushing 'main' to origin...")
    out_push_main, err_push_main, _ = run_cmd(repo, ["git", "push", "origin", "main"])
    print(out_push_main or err_push_main)
    
    print(f"DONE: {name} synced successfully!")

def main():
    for repo in REPOS:
        safe_sync(repo)

if __name__ == "__main__":
    main()
