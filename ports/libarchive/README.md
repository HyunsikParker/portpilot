# libarchive v3.8.11 on QNX 8.0

Upstream: https://github.com/libarchive/libarchive.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 816 of 1137 CTest entries pass

Entries that did not pass:

- `libarchive_test_7zip_filename_encoding_UTF16_win`: skip (exit 2)
- `libarchive_test_acl_platform_nfs4`: skip (exit 2)
- `libarchive_test_acl_platform_posix1e_restore`: skip (exit 2)
- `libarchive_test_acl_platform_posix1e_read`: skip (exit 2)
- `libarchive_test_archive_md5`: skip (exit 2)
- `libarchive_test_archive_rmd160`: skip (exit 2)
- `libarchive_test_archive_sha1`: skip (exit 2)
- `libarchive_test_archive_sha256`: skip (exit 2)
- `libarchive_test_archive_sha384`: skip (exit 2)
- `libarchive_test_archive_sha512`: skip (exit 2)
- `libarchive_test_archive_string_conversion`: skip (exit 2)
- `libarchive_test_archive_string_conversion_fail_c`: fail (exit 1)
- `libarchive_test_archive_string_conversion_fail_latin1`: skip (exit 2)
- `libarchive_test_archive_string_conversion_utf16_utf8`: skip (exit 2)
- `libarchive_test_archive_string_conversion_utf8_utf16`: skip (exit 2)
- `libarchive_test_archive_string_update_utf8_win`: skip (exit 2)
- `libarchive_test_archive_string_update_utf8_utf8`: skip (exit 2)
- `libarchive_test_archive_string_update_utf8_koi8`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_grzip`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_lrzip`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_lz4`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_lzop`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_b64encode`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_zstd`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_by_name_grzip`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_by_name_lrzip`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_by_name_lz4`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_by_name_lzop`: skip (exit 2)
- `libarchive_test_archive_write_add_filter_by_name_zstd`: skip (exit 2)
- `libarchive_test_archive_write_set_format_by_name_xar`: skip (exit 2)
- ... 291 more

## Changes

- linker launcher: object list to ld in its own response file (Windows command-line limit)

## Reproduce

```
python -m portpilot port libarchive https://github.com/libarchive/libarchive.git v3.8.11 --cmake=-DENABLE_TEST=ON --cmake=-DENABLE_OPENSSL=OFF
```
