plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.rajmacwan.routemock"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.rajmacwan.routemock"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        // A human-readable build id shown in the app, passed by CI as
        // -PbuildLabel="b<run#>-<shortSHA>"; defaults to "local" for IDE builds.
        val buildLabel = (project.findProperty("buildLabel") as String?) ?: "local"
        buildConfigField("String", "BUILD_LABEL", "\"$buildLabel\"")
    }

    buildFeatures {
        buildConfig = true
    }

    // A committed, stable signing key so every build (local or CI) is signed the
    // same way and installs as an update over the previous one — no uninstall
    // needed. Fine for a personal, sideloaded app that is not on the Play Store.
    signingConfigs {
        create("routemock") {
            storeFile = file("routemock.keystore")
            storePassword = "routemock"
            keyAlias = "routemock"
            keyPassword = "routemock"
        }
    }

    buildTypes {
        getByName("debug") {
            signingConfig = signingConfigs.getByName("routemock")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("routemock")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.activity:activity-ktx:1.9.1")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.android.gms:play-services-location:21.3.0")
    implementation("org.osmdroid:osmdroid-android:6.1.20")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
}
