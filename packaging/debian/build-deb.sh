#!/bin/bash
# Build lightmount_<version>-1_all.deb from the working tree, without Debian tooling
# if needed: uses dpkg-deb when available, otherwise ar + tar (same format).
# Usage: packaging/debian/build-deb.sh [output directory, default: dist/]
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
repo=$(readlink -f "$here/../..")
version=$(sed -n "s/^__version__ = '\(.*\)'/\1/p" "$repo/lightmount/__init__.py")
revision=1
out=$(readlink -f "${1:-$repo/dist}")
deb=$out/lightmount_${version}-${revision}_all.deb

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
root=$stage/root
mkdir -p "$root/DEBIAN" "$out"

make -s -C "$repo" DESTDIR="$root" PREFIX=/usr install

doc=$root/usr/share/doc/lightmount
install -m644 "$here/copyright" "$doc/copyright"
gzip -9n -c "$here/changelog" > "$doc/changelog.Debian.gz"

installed_size=$(du -sk --exclude=DEBIAN "$root" | cut -f1)
sed -e "s/@VERSION@/$version-$revision/" -e "s/@INSTALLED_SIZE@/$installed_size/" \
    "$here/control" > "$root/DEBIAN/control"
install -m755 "$here/postinst" "$here/postrm" "$root/DEBIAN/"
(cd "$root" && find usr -type f -print0 | sort -z | xargs -0 md5sum) > "$root/DEBIAN/md5sums"

# Normalized permissions: directories 755, files 644, executables 755
find "$root" -type d -exec chmod 755 {} +
find "$root/usr" -type f -exec chmod 644 {} +
chmod 755 "$root/usr/bin/lightmount" "$root/DEBIAN/postinst" "$root/DEBIAN/postrm"

if command -v dpkg-deb >/dev/null; then
    dpkg-deb --root-owner-group -Zxz --build "$root" "$deb" >/dev/null
else
    tarball() {  # tarball DIR OUTPUT: owned by root, sorted, reproducible mtime
        tar --sort=name --owner=root:0 --group=root:0 --mtime=@0 \
            -C "$1" -cJf "$2" "${@:3}"
    }
    echo '2.0' > "$stage/debian-binary"
    tarball "$root/DEBIAN" "$stage/control.tar.xz" .
    tarball "$root" "$stage/data.tar.xz" --exclude=./DEBIAN .
    rm -f "$deb"
    (cd "$stage" && ar rcD "$deb" debian-binary control.tar.xz data.tar.xz)
fi
echo "$deb"
