# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# collider_em standalone macOS app.
# Resources (musiccoca, spectrostream) are loaded from ~/Documents/Magenta/magenta-rt-v2/resources/
# at runtime — see examples/common/cpp/magenta_paths.h.

set(APP_ICON "${CMAKE_CURRENT_SOURCE_DIR}/../common/assets/AppIcon.icns")
set_source_files_properties(${APP_ICON} PROPERTIES MACOSX_PACKAGE_LOCATION "Resources")

add_executable(collider_em MACOSX_BUNDLE
    ColliderApp.mm
    ColliderAppController.mm
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/cpp/magenta_paths.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/objc/MagentaModelManager.mm
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/objc/MagentaModelDownloader.mm
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/objc/MagentaSettings.mm
    ${APP_ICON}
)

target_include_directories(collider_em PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/objc
)
target_compile_options(collider_em PRIVATE -fobjc-arc)

target_link_libraries(collider_em PRIVATE
    magentart::core
    "-framework AppKit"
    "-framework AudioToolbox"
    "-framework AVFoundation"
    "-framework CoreAudio"
    "-framework CoreMIDI"
    "-framework WebKit"
    "-framework UniformTypeIdentifiers"
)

set_target_properties(collider_em PROPERTIES
    MACOSX_BUNDLE TRUE
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/ColliderInfo.plist.in"
    MACOSX_BUNDLE_EXECUTABLE_NAME collider_em
    MACOSX_BUNDLE_BUNDLE_NAME "Collider - Emotional Magenta"
    MACOSX_BUNDLE_ICON_FILE "AppIcon.icns"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "com.google.collider_em"
)

# ─── Collider React UI Build Target ───────────────────────────────────────────
add_custom_target(build_collider_ui ALL
    COMMAND npm run build
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/ui
    COMMENT "Building Collider UI..."
)
add_dependencies(build_collider_ui npm_install_root)
add_dependencies(collider_em build_collider_ui)

# ─── Deploy standalone app ───────────────────────────────────────────────────
add_custom_target(deploy_collider_em
    DEPENDS collider_em
    # Copy Collider UI dist into app Resources
    COMMAND ${CMAKE_COMMAND} -E make_directory
        "$<TARGET_BUNDLE_DIR:collider_em>/Contents/Resources/collider_ui"
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        "${CMAKE_CURRENT_SOURCE_DIR}/ui/dist"
        "$<TARGET_BUNDLE_DIR:collider_em>/Contents/Resources/collider_ui"
    # Bundle emotion bridge script used to push live emotion prompt updates
    COMMAND ${CMAKE_COMMAND} -E copy
        "${CMAKE_CURRENT_SOURCE_DIR}/collider_emotion_bridge.py"
        "$<TARGET_BUNDLE_DIR:collider_em>/Contents/Resources/collider_emotion_bridge.py"
    # Copy mlx.metallib next to the binary
    COMMAND ${CMAKE_COMMAND} -E copy
        "${mlx_BINARY_DIR}/mlx/backend/metal/kernels/mlx.metallib"
        "$<TARGET_BUNDLE_DIR:collider_em>/Contents/MacOS/mlx.metallib"
    # Code sign
    COMMAND codesign ${CODESIGN_FLAGS}
        "$<TARGET_BUNDLE_DIR:collider_em>/Contents/MacOS/mlx.metallib"
    COMMAND codesign ${CODESIGN_FLAGS}
        --entitlements "${CMAKE_CURRENT_SOURCE_DIR}/ColliderEntitlements.plist"
        --generate-entitlement-der
        "$<TARGET_BUNDLE_DIR:collider_em>"
    # Deploy to ~/Applications
    COMMAND ${CMAKE_COMMAND} -E remove_directory
        "$ENV{HOME}/Applications/collider_em.app"
    COMMAND ditto
        "$<TARGET_BUNDLE_DIR:collider_em>"
        "$ENV{HOME}/Applications/collider_em.app"
    COMMENT "Building and deploying collider_em standalone app"
    VERBATIM
)

# Notarize the deployed collider_em.app (requires Developer ID).
magentart_add_notarize_target(notarize_collider_em
    APP "$ENV{HOME}/Applications/collider_em.app"
    DEPENDS deploy_collider_em
    ZIP_NAME "collider_em.zip"
)
