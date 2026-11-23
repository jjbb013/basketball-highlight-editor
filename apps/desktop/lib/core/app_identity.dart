import 'dart:io';

String appDisplayName({bool? isMacOS}) =>
    (isMacOS ?? Platform.isMacOS) ? 'BHE Pro' : 'BHE';
