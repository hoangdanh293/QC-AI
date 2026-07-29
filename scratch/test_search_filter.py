import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from core.drive_manager import (
    load_drive_config,
    authenticate_drive,
    search_files_global
)

def main():
    cfg = load_drive_config()
    print("Drive Config:")
    print(f"  Auth Type: {cfg.get('auth_type')}")
    print(f"  Credentials: {cfg.get('credentials_file')}")
    print(f"  Root Folder ID: {cfg.get('root_folder_id')}")
    
    try:
        service = authenticate_drive(cfg)
        if not service:
            print("Failed to authenticate drive service.")
            return
        
        print("\nAuthenticated successfully. Running search...")
        
        root_id = cfg.get("root_folder_id", "")
        # We can search for a common term or empty term just to see results
        results = search_files_global(
            service,
            root_folder_id=root_id,
            name_query="Maltitol",  # Or something else
            max_results=5
        )
        
        print(f"\nFound {len(results)} files:")
        for idx, f in enumerate(results, 1):
            print(f"{idx}. Name: {f.get('name')}")
            print(f"   ID: {f.get('id')}")
            parents = f.get('parents', [])
            print(f"   Parents: {parents}")
            if parents:
                from core.drive_manager import get_folder_path
                path = get_folder_path(service, parents[0])
                path_str = " -> ".join([f"{p['name']} ({p['id']})" for p in path])
                print(f"   Breadcrumb: {path_str}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
