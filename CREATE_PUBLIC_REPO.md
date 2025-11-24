# Creating a New Public Repository

This guide walks you through creating a clean public repository without sensitive data from git history.

## Security Verification Complete ✓

The following security checks have been completed:
- ✓ No hardcoded credentials in tracked files
- ✓ `.gitignore` properly configured to exclude sensitive files
- ✓ Only example credential files are tracked
- ✓ Database files properly excluded

## Steps to Create New Public Repository

### 1. Create New Repository on GitHub

1. Go to https://github.com/new
2. Choose a repository name (e.g., `woodlander-order-flow`)
3. Set visibility to **Public**
4. Do NOT initialize with README, .gitignore, or license
5. Click "Create repository"

### 2. Prepare Current Repository

The current repository has been cleaned and committed. The latest commit removes all hardcoded credentials.

```bash
# View the security fix commit
git log -1 --stat
```

### 3. Push to New Repository

GitHub will provide commands after creating the repository. Use the "push an existing repository" option:

```bash
# Add new remote (replace with your new repo URL)
git remote add public https://github.com/YOUR-USERNAME/YOUR-NEW-REPO.git

# Push all branches and tags
git push -u public main

# Optional: Push all tags if you have any
git push public --tags
```

### 4. Verify the New Repository

After pushing, verify on GitHub:
- ✓ Check that no credential files exist (`odoosys.py`, `*_cred.py`)
- ✓ Review `.gitignore` is present
- ✓ Verify example files have placeholder values only
- ✓ Check recent commits don't contain sensitive data

### 5. Update Repository Settings (Optional)

On GitHub, you can:
- Add repository description
- Add topics/tags for discoverability
- Enable/disable features (Issues, Wiki, Discussions)
- Add a license if appropriate

### 6. Clean Up Old Repository

Once the new public repository is confirmed working:

```bash
# Optional: Remove old remote or rename it
git remote rename origin old-private

# Or keep both remotes
git remote -v  # List all remotes
```

## Important Notes

### Files Excluded by .gitignore

The following sensitive files are automatically excluded:
- `odoosys.py` - Odoo credentials
- `shopify_export_cred.py` - Shopify credentials
- `*_cred.py` - Any credential files
- `*.db` - Database files
- `*.csv` - CSV exports (except specific whitelisted files)
- `*.log` - Log files

### Example Files Included

These example files are safe to include:
- `Order_Flow/shopify_export_cred_example.py`
- `Shopify_Odoo_Stock_Cross_Ref/shopify_export_cred_example.py`
- `Shopify_Odoo_Stock_Cross_Ref/shopify_cred_store2_example.py`

All example files contain only placeholder values (e.g., `shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).

### Setup Instructions for New Users

Users cloning the new public repository will need to:

1. Create `odoosys.py` in the root directory:
   ```python
   url = 'https://your-instance.odoo.com'
   db = 'your_database_name'
   username = 'your_username'
   password = 'your_password'
   ```

2. Copy and configure Shopify credentials:
   ```bash
   cp Order_Flow/shopify_export_cred_example.py Order_Flow/shopify_export_cred.py
   # Edit with your actual credentials
   ```

3. Install dependencies:
   ```bash
   pip install -r Shopify_Odoo_Stock_Cross_Ref/requirements.txt
   ```

## Troubleshooting

### If you accidentally push sensitive data:

1. **Immediately** change all exposed credentials
2. Delete the public repository on GitHub
3. Create a new one following this guide
4. Do NOT attempt to rewrite history on a public repository

### If you need to keep both repositories:

```bash
# Keep both remotes with different names
git remote rename origin private
git remote add public https://github.com/YOUR-USERNAME/YOUR-NEW-REPO.git

# Push to specific remote
git push private main
git push public main
```

## Next Steps

After creating the public repository:
1. Update any documentation references to the new repository URL
2. Add a comprehensive README.md if not already present
3. Consider adding contribution guidelines (CONTRIBUTING.md)
4. Add issue templates for bug reports and feature requests
