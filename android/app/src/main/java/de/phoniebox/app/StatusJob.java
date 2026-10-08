package de.phoniebox.app;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;

/**
 * Fragt die Box im Hintergrund etwa alle 15 Minuten (das kürzeste, was Android erlaubt) nach
 * Problemen, solange das Handy in einem WLAN ist. Ist die Box nicht erreichbar, etwa weil das
 * Handy nicht zu Hause ist, bleibt alles, wie es ist.
 */
public class StatusJob extends JobService {
    private static final int JOB = 1;
    private static final long INTERVAL = 15 * 60 * 1000L;

    static void schedule(Context context) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (scheduler.getPendingJob(JOB) != null) {
            return;
        }
        scheduler.schedule(new JobInfo.Builder(JOB, new ComponentName(context, StatusJob.class))
                .setPeriodic(INTERVAL)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)
                .setPersisted(true)
                .build());
    }

    static void cancel(Context context) {
        context.getSystemService(JobScheduler.class).cancel(JOB);
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try {
                Notifier.apply(this, Box.status(this));
            } catch (Exception ignored) {
                // Nicht im Heim-WLAN oder Box aus: beim nächsten Mal erneut.
            }
            jobFinished(params, false);
        }, "phoniebox-status").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return false;
    }
}
