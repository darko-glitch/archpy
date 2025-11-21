#!/bin/python3

# Modules import
from modules import parse_arguments, loadYamlFromFile
import subprocess
import os
import sys
import getpass

class colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class STATUS:
    PROGRESS = '[. ]'
    OK = f'{colors.OKGREEN}✔{colors.ENDC}'
    ERROR = f'{colors.FAIL}✘{colors.ENDC}'

class Executor:
    ULTRALOG = False
    LOGERROR = False

    @staticmethod
    def execute(command: str):
        if Executor.ULTRALOG:
            os.system(command)
            return 0
        elif Executor.LOGERROR:
            process = subprocess.run(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if process.returncode != 0:
                print(f"\nError output: {process.stderr.decode()}", file=sys.stderr)
            return process.returncode
        else:
            process = subprocess.run(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            return process.returncode

def execute(command: str, description: str):
    # Get terminal width, default to 80 if unavailable
    try:
        terminal_width = os.get_terminal_size().columns
    except:
        terminal_width = 80
    
    message = f'{STATUS.PROGRESS} {description}'
    # Pad message to clear any previous text
    padded_message = message.ljust(terminal_width)
    print(padded_message, end='\r', flush=True)
    
    returncode = Executor.execute(command)
    
    if returncode == 0:
        message = f'{STATUS.OK} {description}'
        padded_message = message.ljust(terminal_width)
        print(padded_message)
    else:
        message = f'{STATUS.ERROR} {description}'
        padded_message = message.ljust(terminal_width)
        print(padded_message)
    
    return returncode

def execute_chroot(command: str, description: str):
    """Execute command in chroot environment"""
    chroot_command = f'arch-chroot /mnt {command}'
    return execute(chroot_command, description)

def setKeyMap(keymap: str):
    description = f'Setting keymap to {keymap}'
    command = f'loadkeys {keymap}'
    return execute(command, description)

def cryptPartition(linux_partition: str, password: str = None):
    description = 'Encrypting partition with LUKS'
    if password:
        command = f'echo -n "{password}" | cryptsetup luksFormat --batch-mode --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --pbkdf argon2id --pbkdf-memory 4194304 --pbkdf-parallel 4 --iter-time 4000 {linux_partition} -'
    else:
        command = f'cryptsetup luksFormat --batch-mode --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --pbkdf argon2id --pbkdf-memory 4194304 --pbkdf-parallel 4 --iter-time 4000 {linux_partition}'
    return execute(command, description)

def cryptOpen(linux_partition: str, password: str = None):
    description = 'Opening encrypted partition'
    if password:
        command = f'echo -n "{password}" | cryptsetup open {linux_partition} cryptroot -'
    else:
        command = f'cryptsetup open {linux_partition} cryptroot'
    return execute(command, description)

def formatBtrfs(crypted_root_device: str):
    description = f'Formatting {crypted_root_device} with Btrfs'
    command = f'mkfs.btrfs -f {crypted_root_device}'
    return execute(command, description)

def creatingSubvol():
    subvolumes = ['@', '@home', '@var', '@tmp', '@snapshots']
    for subvol in subvolumes:
        description = f'Creating Btrfs subvolume {subvol}'
        command = f'btrfs subvolume create /mnt/{subvol}'
        returncode = execute(command, description)
        if returncode != 0:
            return returncode

    description = 'Unmounting temporary mount'
    command = 'umount /mnt'
    return execute(command, description)

def mountBtrfsSubvolumes(crypted_root_device: str):
    description = f'Mounting Btrfs subvolume @ to /mnt'
    command = f'mount -o compress=zstd,subvol=@ {crypted_root_device} /mnt'
    returncode = execute(command, description)
    if returncode != 0:
        return returncode

    description = 'Creating mount points for subvolumes'
    command = 'mkdir -p /mnt/{home,var,tmp,.snapshots,boot}'
    returncode = execute(command, description)
    if returncode != 0:
        return returncode

    subvolumes = ['@home', '@var', '@tmp', '@snapshots']
    mountpoints = ['home', 'var', 'tmp', '.snapshots']

    for subvol, mnt in zip(subvolumes, mountpoints):
        description = f'Mounting Btrfs subvolume {subvol} to /mnt/{mnt}'
        command = f'mount -o compress=zstd,subvol={subvol} {crypted_root_device} /mnt/{mnt}'
        returncode = execute(command, description)
        if returncode != 0:
            return returncode
    
    return 0

def installPackage(package: str):
    description = f'Installing {package}'
    command = f'basestrap /mnt {package} --noconfirm'
    return execute(command, description)

def serviceEnable(service: str):
    description = f'Enabling OpenRC service {service}'
    command = f'rc-update add {service} default'
    return execute_chroot(command, description)

def mountEfiPartition(efi_partition: str, path: str ="boot"):
    description = f'Mounting EFI partition to {path}'
    command = f'mkdir -p /mnt{path} && mount {efi_partition} /mnt{path}'
    return execute(command, description)

def generateFstab():
    description = 'Generating fstab'
    command = 'fstabgen -U /mnt >> /mnt/etc/fstab'
    return execute(command, description)

def copyInstallerInMNT():
    description = 'Copying installer to /mnt'
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    command = f'cp -r {parent_dir}/archpy /mnt/'
    return execute(command, description)

def chrootAndExecute(config_path: str = '/archpy/config.yml', installer_path: str = '/archpy/installer.py'):
    description = 'Running chroot installation'
    command = f'arch-chroot /mnt python3 {installer_path} {config_path} --chroot' + \
        (' --logerror' if Executor.LOGERROR else '') + \
        (' --ultralog' if Executor.ULTRALOG else '')
    returncode = os.system(command)
    return returncode

def linkTime(region: str, location: str):
    description = f'Linking time to {region}/{location}'
    command = f'ln -sf /usr/share/zoneinfo/{region}/{location} /etc/localtime'
    return execute(command, description)

def setHwClock():
    description = 'Setting hardware clock'
    command = 'hwclock --systohc'
    return execute(command, description)

def addLocale(locale: str):
    description = f'Adding locale {locale}'
    command = f'echo "{locale}" >> /etc/locale.gen && locale-gen'
    return execute(command, description)

def addLang(lang: str):
    description = f'Setting system language to {lang}'
    command = f'echo "LANG={lang}" > /etc/locale.conf'
    return execute(command, description)

def addHostname(hostname: str):
    description = f'Setting hostname to {hostname}'
    command = f'echo "{hostname}" > /etc/hostname'
    return execute(command, description)

def setupHosts(hostname: str = 'artix'):
    description = 'Configuring /etc/hosts'
    command = f'echo -e "127.0.0.1\\tlocalhost\\n127.0.1.1\\t{hostname}.localdomain\\t{hostname}" > /etc/hosts'
    return execute(command, description)

def createUser(username: str, password: str):
    description = f'Creating user {username}'
    command = f'useradd -m -G wheel,storage,power,audio,video "{username}" && echo "{username}:{password}" | chpasswd'
    return execute(command, description)

def addWheelToSudoers():
    description = 'Adding wheel group to sudoers'
    command = 'echo "%wheel ALL=(ALL:ALL) ALL" >> /etc/sudoers'
    return execute(command, description)

def setMkinitcpioHooks():
    description = 'Configuring mkinitcpio for LUKS'
    command = "sed -i 's/^HOOKS=.*/HOOKS=(base udev autodetect microcode modconf kms keyboard keymap consolefont block encrypt filesystems fsck)/' /etc/mkinitcpio.conf"
    return execute(command, description)

def mkinit():
    description = 'Generating initial ramdisk'
    command = 'mkinitcpio -P'
    return execute(command, description)

def grubConfig(linux_partition: str, crypted_root_device: str):
    description = 'Configuring GRUB for encrypted root'
    
    # Get UUIDs
    linux_uuid = get_disk_uuid(linux_partition)
    crypted_uuid = get_disk_uuid(crypted_root_device)
    
    if not linux_uuid or not crypted_uuid:
        print(f'{STATUS.ERROR} Failed to get disk UUIDs')
        return 1
    
    command = (
        f'sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|'
        f'GRUB_CMDLINE_LINUX_DEFAULT=\\"loglevel=3 quiet '
        f'cryptdevice=UUID={linux_uuid}:cryptroot root=UUID={crypted_uuid}\\"|" '
        f'/etc/default/grub'
    )
    
    return execute(command, description)

def grubInstall(target, efi_directory, bootloader_id):
    description = f'Installing GRUB bootloader'
    command = f'grub-install --target={target} --efi-directory={efi_directory} --bootloader-id={bootloader_id} --recheck'
    return execute(command, description)

def mkconfig():
    description = 'Generating GRUB configuration'
    command = 'grub-mkconfig -o /boot/grub/grub.cfg'
    return execute(command, description)

def get_disk_uuid(disk: str):
    """Get UUID of a disk/partition"""
    try:
        result = subprocess.run(
            ["blkid", "-s", "UUID", "-o", "value", disk],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def setPasswdForRoot(password: str):
    description = 'Setting root password'
    command = f'echo "root:{password}" | chpasswd'
    return execute(command, description)

def setVconsoleKeymap(keymap: str):
    description = 'Configuring console keymap'
    command = f'echo "KEYMAP={keymap}" > /etc/vconsole.conf'
    return execute(command, description)

def get_secure_password(prompt: str, min_length: int = 6):
    """Get password securely with confirmation"""
    while True:
        try:
            password = getpass.getpass(f"{prompt}: ")
            if len(password) < min_length:
                print(f'{colors.WARNING}Password must be at least {min_length} characters!{colors.ENDC}')
                continue
            
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print(f'{colors.WARNING}Passwords do not match! Try again.{colors.ENDC}')
                continue
            
            return password
        except (KeyboardInterrupt, EOFError):
            print(f'\n{colors.FAIL}Password input cancelled{colors.ENDC}')
            sys.exit(1)

def reboot():
    print("\n" + colors.OKGREEN + colors.BOLD + "Installation completed successfully!" + colors.ENDC)
    print("\nImportant: Remove installation media before rebooting")
    response = input("\nPress Enter to reboot or Ctrl+C to exit: ")
    os.system('reboot')

def archiso(data):
    partitions = data['partitions']
    boot = data['boot']
    settings = data['settings']
    packages = data['packages']

    print(f"\n{colors.HEADER}{colors.BOLD}=== Artix Linux Installation ==={colors.ENDC}\n")

    # Set keymap
    keymap = settings['keymap']
    if setKeyMap(keymap) != 0:
        print(f'{colors.FAIL}Failed to set keymap. Continuing...{colors.ENDC}')

    # Get LUKS encryption password
    linux_partition = partitions['linux']
    print(f"\n{colors.BOLD}LUKS Encryption Setup{colors.ENDC}")
    print(f"Partition: {linux_partition}")
    cryptpassword = get_secure_password("Enter password for LUKS encryption", min_length=8)
    
    # Encrypt and open partition
    if cryptPartition(linux_partition, cryptpassword) != 0:
        print(f'{colors.FAIL}Failed to encrypt partition!{colors.ENDC}')
        sys.exit(1)
    
    if cryptOpen(linux_partition, cryptpassword) != 0:
        print(f'{colors.FAIL}Failed to open encrypted partition!{colors.ENDC}')
        sys.exit(1)

    # Configure Btrfs
    crypted_root_device = "/dev/mapper/cryptroot"
    
    if formatBtrfs(crypted_root_device) != 0:
        print(f'{colors.FAIL}Failed to format Btrfs!{colors.ENDC}')
        sys.exit(1)
    
    # Mount temporarily to create subvolumes
    if execute(f'mount {crypted_root_device} /mnt', 'Mounting for subvolume creation') != 0:
        print(f'{colors.FAIL}Failed to mount partition!{colors.ENDC}')
        sys.exit(1)
    
    if creatingSubvol() != 0:
        print(f'{colors.FAIL}Failed to create subvolumes!{colors.ENDC}')
        sys.exit(1)
    
    if mountBtrfsSubvolumes(crypted_root_device) != 0:
        print(f'{colors.FAIL}Failed to mount Btrfs subvolumes!{colors.ENDC}')
        sys.exit(1)

    # Mount EFI partition
    efi_partition = partitions['efi']
    path = "boot"
    if mountEfiPartition(efi_partition, path) != 0:
        print(f'{colors.FAIL}Failed to mount EFI partition!{colors.ENDC}')
        sys.exit(1)

    # Install packages
    print(f"\n{colors.BOLD}Installing packages...{colors.ENDC}")
    failed_packages = []
    for package in packages:
        if installPackage(package) != 0:
            failed_packages.append(package)
    
    if failed_packages:
        print(f'{colors.WARNING}Warning: Failed to install: {", ".join(failed_packages)}{colors.ENDC}')

    # Generate fstab
    if generateFstab() != 0:
        print(f'{colors.FAIL}Failed to generate fstab!{colors.ENDC}')
        sys.exit(1)

    # Copy installer to /mnt
    if copyInstallerInMNT() != 0:
        print(f'{colors.FAIL}Failed to copy installer!{colors.ENDC}')
        sys.exit(1)

    # Chroot and execute
    print(f"\n{colors.BOLD}Entering chroot environment...{colors.ENDC}\n")
    if chrootAndExecute() != 0:
        print(f'{colors.FAIL}Chroot installation failed!{colors.ENDC}')
        sys.exit(1)

    # Reboot
    reboot()

def chroot(data):
    partitions = data['partitions']
    boot = data['boot']
    settings = data['settings']
    services = data.get('services', [])
    accounts = data['accounts']

    print(f"\n{colors.HEADER}{colors.BOLD}=== Chroot Configuration ==={colors.ENDC}\n")

    # Link time
    region = settings['region']
    location = settings['location']
    linkTime(region, location)

    # Set hardware clock
    setHwClock()

    # Add locale
    locale = settings['locale']
    addLocale(locale)

    # Add lang
    lang = settings['lang']
    addLang(lang)

    # Add hostname
    hostname = settings['hostname']
    addHostname(hostname)

    # Setup hosts
    setupHosts(hostname)

    # Set vconsole keymap for persistence
    keymap = settings['keymap']
    setVconsoleKeymap(keymap)

    # Configure mkinitcpio BEFORE running it
    setMkinitcpioHooks()
    
    # Generate initramfs
    mkinit()

    # Configure GRUB for encrypted root
    linux_partition = partitions['linux']
    crypted_root_device = "/dev/mapper/cryptroot"
    grubConfig(linux_partition, crypted_root_device)

    # Install GRUB
    target = boot['target']
    efi_directory = boot['efi-directory']
    bootloader_id = boot['bootloader-id']
    grubInstall(target, efi_directory, bootloader_id)

    # Generate GRUB config
    mkconfig()

    # Set root password
    print(f"\n{colors.BOLD}Root Account Setup{colors.ENDC}")
    root_password = get_secure_password("Enter password for root")
    setPasswdForRoot(root_password)

    # Create user
    username = accounts['username']
    print(f"\n{colors.BOLD}User Account Setup for '{username}'{colors.ENDC}")
    user_password = get_secure_password(f"Enter password for user '{username}'")
    createUser(username, user_password)

    # Add wheel to sudoers
    addWheelToSudoers()

    # Enable services
    print(f"\n{colors.BOLD}Enabling services...{colors.ENDC}")
    for service in services:
        serviceEnable(service)

    print(f"\n{colors.OKGREEN}{colors.BOLD}Chroot configuration completed!{colors.ENDC}\n")

if __name__ == "__main__":
    args = parse_arguments()
    configurationFilePath = args.file
    
    try:
        data = loadYamlFromFile(configurationFilePath)
    except Exception as e:
        print(f'{colors.FAIL}Error loading configuration: {e}{colors.ENDC}')
        sys.exit(1)

    if args.ultralog:
        Executor.ULTRALOG = True
    if args.logerror:
        Executor.LOGERROR = True

    try:
        if args.chroot:
            chroot(data)
        else:
            archiso(data)
    except KeyboardInterrupt:
        print(f'\n{colors.FAIL}Installation cancelled by user{colors.ENDC}')
        sys.exit(1)
    except Exception as e:
        print(f'\n{colors.FAIL}Unexpected error: {e}{colors.ENDC}')
        sys.exit(1)