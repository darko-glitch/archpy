#!/bin/python3

# Modules import
from modules import parse_arguments, loadYamlFromFile
import subprocess
import os
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
    OK = f'{colors.OKGREEN}\u2714{colors.ENDC}'
    ERROR = f'{colors.FAIL}\u2718{colors.ENDC}'

class Executor:
    ULTRALOG = False
    LOGERROR = False

    @staticmethod
    def execute(command: str):
        if Executor.ULTRALOG:
            os.system(command)
            return 0
        elif Executor.LOGERROR:
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE)
            process.wait()
            
            process = subprocess.run(
                command, shell=True, stdout=subprocess.PIPE)
            return process.returncode
        else:
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            process.wait()
            
            process = subprocess.run(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            return process.returncode

def execute(command: str, description: str):
    message = f'{STATUS.PROGRESS} {description}'
    print(message, end='\r', flush=True)
    returncode = Executor.execute(command)
    if returncode == 0:
        message = f'{STATUS.OK} {description}'
        print(f'\r{message}')
    else:
        message = f'{STATUS.ERROR} {description}'
        print(f'\r{message}')
    return returncode

def execute_chroot(command: str, description: str):
    """Execute command in chroot environment"""
    chroot_command = f'arch-chroot /mnt {command}'
    return execute(chroot_command, description)

def setKeyMap(keymap: str):
    description = f'Settings keymap to {keymap}'
    command = f'loadkeys {keymap}'
    execute(command, description)

def cryptPartition(linux_partition: str, password: str = None):
    description = f'Crypting Partition.'
    if password:
        command = f'echo -n "{password}" | cryptsetup luksFormat --batch-mode --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --pbkdf argon2id --pbkdf-memory 8589934592 --pbkdf-parallel 4 --pbkdf-time 4 {linux_partition} -'
    else:
        command = f'cryptsetup luksFormat --batch-mode --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --pbkdf argon2id --pbkdf-memory 8589934592 --pbkdf-parallel 4 --pbkdf-time 4 {linux_partition}'
    execute(command, description)

def cryptOpen(linux_partition: str, password: str = None):
    description = f'Opening encrypted partition.'
    if password:
        command = f'echo -n "{password}" | cryptsetup open {linux_partition} cryptroot -'
    else:
        command = f'cryptsetup open {linux_partition} cryptroot'
    execute(command, description)

def formatBtrfs(crypted_root_device: str):
    description = f'Formatting {crypted_root_device} with Btrfs'
    command = f'mkfs.btrfs {crypted_root_device}'
    execute(command, description)

def creatingSubvol():
    subvolumes = ['@', '@home', '@var', '@tmp', '@snapshots']
    for subvol in subvolumes:
        description = f'Creating Btrfs subvolume {subvol}'
        command = f'btrfs subvolume create /mnt/{subvol}'
        execute(command, description)

    description = 'Unmounting temporary mount'
    command = 'umount /mnt'
    execute(command, description)

def mountBtrfsSubvolumes(crypted_root_device: str):
    description = f'Mounting Btrfs subvolume @ to /mnt with compress=zstd'
    command = f'mount -o compress=zstd,subvol=@ {crypted_root_device} /mnt'
    execute(command, description)

    description = 'Creating mount points for subvolumes'
    command = 'mkdir -p /mnt/{home,var,tmp,.snapshots,boot}'
    execute(command, description)

    subvolumes = ['@home', '@var', '@tmp', '@snapshots']
    mountpoints = ['home', 'var', 'tmp', '.snapshots']

    for subvol, mnt in zip(subvolumes, mountpoints):
        description = f'Mounting Btrfs subvolume {subvol} to /mnt/{mnt}'
        command = f'mount -o compress=zstd,subvol={subvol} {crypted_root_device} /mnt/{mnt}'
        execute(command, description)

def installPackage(package: str):
    description = f'Installing {package}'
    command = f'basestrap /mnt {package} --noconfirm'
    execute(command, description)

def serviceEnable(service: str):
    description = f'Enabling OpenRC service {service}'
    command = f'rc-update add {service} default'
    execute_chroot(command, description)

def mountLinuxPartition(crypted_root_device: str):
    description = f'Mounting {crypted_root_device} to /mnt'
    command = f"mount {crypted_root_device} /mnt"
    execute(command, description)

def mountEfiPartition(efi_partition: str, path: str):
    description = f'Mounting Efi Partition from {efi_partition} to {path}'
    command = f'mkdir -p /mnt{path}; mount {efi_partition} /mnt{path}'
    execute(command, description)

def generateFstab():
    description = 'Generating fstab'
    command = 'fstabgen -U /mnt >> /mnt/etc/fstab'
    execute(command, description)

def copyInstallerInMNT():
    description = 'Copying installer to /mnt'
    command = 'cp -r ../archinstaller /mnt'
    execute(command, description)

def chrootAndExecute(config_path: str = '/archinstaller/config.yml', installer_path: str = '/archinstaller/installer.py'):
    description = 'Running chroot'
    command = f'arch-chroot /mnt {installer_path} {config_path} --chroot' + \
        (' --logerror' if Executor.LOGERROR else '')
    os.system(command)

def linkTime(region: str, location: str):
    description = f'Linking time to {region}/{location}'
    command = f'ln -sf /usr/share/zoneinfo/{region}/{location} /etc/localtime'
    execute(command, description)

def setHwClock():
    description = 'Setting hwclock'
    command = 'hwclock --systohc'
    execute(command, description)

def addLocale(locale: str):
    description = f'Adding locale {locale}'
    command = f'echo {locale} >> /etc/locale.gen; locale-gen'
    execute(command, description)

def addLang(lang: str):
    description = f'Adding lang {lang}'
    command = f'echo "LANG={lang}" >> /etc/locale.conf'
    execute(command, description)

def addHostname(hostname: str):
    description = f'Adding hostname {hostname}'
    command = f'echo "{hostname}" > /etc/hostname'
    execute(command, description)

def setupHosts(hostname: str = 'artix'):
    description = 'Setting up hosts'
    command = f'echo "127.0.0.1 localhost\n127.0.1.1 {hostname}.localdomain {hostname}" > /etc/hosts'
    execute(command, description)

def createUser(username: str, password: str):
    description = f'Creating user {username}'
    command = f'useradd -m -G wheel,storage,power,audio,video "{username}"; echo -e "{password}\n{password}" | passwd {username}'
    execute(command, description)

def addWheelToSudoers():
    description = 'Adding wheel group to sudoers'
    command = 'echo "%wheel ALL=(ALL) ALL" | EDITOR="tee -a" visudo'
    execute(command, description)

def setMkinitcpioHooks():
    description = 'Setting mkinitcpio HOOKS for LUKS'
    command = "sed -i 's/^HOOKS=.*/HOOKS=(base udev autodetect microcode modconf kms keyboard keymap consolefont block filesystems fsck)/' /etc/mkinitcpio.conf"
    execute(command, description)

def mkinit():
    description = 'Running mkinitcpio'
    command = 'mkinitcpio -P'
    execute(command, description)

def grubConfig(linux_partition: str, crypted_root_device: str):
    description = 'Setting GRUB_CMDLINE_LINUX_DEFAULT for LUKS'
    
    # Get UUIDs
    linux_uuid = get_disk_uuid(linux_partition)
    crypted_uuid = get_disk_uuid(crypted_root_device)
    
    command = (
        f'sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|'
        f'GRUB_CMDLINE_LINUX_DEFAULT=\\"loglevel=3 rhgb quiet mitigations=off '
        f'cryptdevice=UUID={linux_uuid}:cryptroot root=UUID={crypted_uuid}\\"|" '
        f'/etc/default/grub'
    )
    
    execute(command, description)

def grubInstall(target, efi_directory, bootloader_id):
    description = f'Installing GRUB to {target}'
    command = f'grub-install --target={target} --efi-directory={efi_directory} --bootloader-id={bootloader_id} --recheck'
    execute(command, description)

def mkconfig():
    description = 'Generating GRUB config'
    command = 'grub-mkconfig -o /boot/grub/grub.cfg'
    execute(command, description)

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
    except subprocess.CalledProcessError as e:
        print(f'{STATUS.ERROR} Failed to get UUID for {disk}')
        return None

def setPasswForRoot(password: str):
    description = f'Setting root password to {password}'
    command = f'echo -e "{password}\n{password}" | passwd root'
    execute(command, description)

def reboot():
    print("\n\nInstallation completed!!\n\n")
    input("Press enter to reboot")
    os.system('reboot')

def archiso(data):
    partitions = data['partitions']
    boot = data['boot']
    settings = data['settings']
    packages = data['packages']

    # Set keymap
    keymap = settings['keymap']
    setKeyMap(keymap)

    # Crypt root partition - use getpass for security
    linux_partition = partitions['linux']
    print("\n" + colors.BOLD + "LUKS Encryption Setup" + colors.ENDC)
    cryptpassword = getpass.getpass("Enter password for LUKS encryption: ")
    cryptpassword_confirm = getpass.getpass("Confirm password: ")
    
    if cryptpassword != cryptpassword_confirm:
        print(f'{STATUS.ERROR} Passwords do not match!')
        exit(1)
    
    if len(cryptpassword) < 8:
        print(f'{STATUS.ERROR} Password must be at least 8 characters!')
        exit(1)
    
    cryptPartition(linux_partition, cryptpassword)
    cryptOpen(linux_partition, cryptpassword)

    # Configure Btrfs 
    crypted_root_device = "/dev/mapper/cryptroot"
    formatBtrfs(crypted_root_device)
    
    # Mount temporarily to create subvolumes
    execute(f'mount {crypted_root_device} /mnt', 'Mounting temporarily for subvolume creation')
    creatingSubvol()
    
    # Mount with proper subvolume options
    mountBtrfsSubvolumes(crypted_root_device)

    # Mounting efi partition
    efi_partition = partitions['efi']
    efi_directory = boot['efi-directory']
    mountEfiPartition(efi_partition, efi_directory)

    # Installing packages
    for package in packages:
        installPackage(package)

    # Generate fstab
    generateFstab()

    # Copying installer to /mnt
    copyInstallerInMNT()

    # Chroot and execute
    chrootAndExecute()

    # Rebooting
    reboot()

def chroot(data):
    partitions = data['partitions']
    boot = data['boot']
    settings = data['settings']
    packages = data['packages']
    accounts = data['accounts']
    services = data.get('services', [])

    # Link time
    region = settings['region']
    location = settings['location']
    linkTime(region, location)

    # Set hwclock
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

    # Set keymap persistence
    keymap = settings['keymap']
    description = f'Setting vconsole keymap to {keymap}'
    command = f'echo "KEYMAP={keymap}" > /etc/vconsole.conf'
    execute(command, description)

    # Configure mkinitcpio BEFORE running it
    setMkinitcpioHooks()
    
    # Run mkinitcpio
    mkinit()

    # Configure GRUB for encrypted root
    linux_partition = partitions['linux']
    crypted_root_device = "/dev/mapper/cryptroot"
    grubConfig(linux_partition, crypted_root_device)

    # Grub install
    target = boot['target']
    efi_directory = boot['efi-directory']
    bootloader_id = boot['bootloader-id']
    grubInstall(target, efi_directory, bootloader_id)

    # Generate GRUB config
    mkconfig()

    # Set root password
    password = accounts['root-password']
    setPasswForRoot(password)

    # Create user
    username = accounts['username']
    password = accounts['password']
    createUser(username, password)

    # Add wheel to sudoers
    addWheelToSudoers()

    # Enable services
    for service in services:
        serviceEnable(service)

    os.system('exit')
    exit(0)


if __name__ == "__main__":
    args = parse_arguments()
    configurationFilePath = args.file
    data = loadYamlFromFile(configurationFilePath)

    if args.ultralog:
        Executor.ULTRALOG = True
    if args.logerror:
        Executor.LOGERROR = True

    if args.chroot:
        chroot(data)
    else:
        archiso(data)


